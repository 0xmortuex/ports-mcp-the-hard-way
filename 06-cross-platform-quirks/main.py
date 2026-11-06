"""Module 06: the places Windows, macOS and Linux disagree - probed for real on THIS machine.

Every check asserts the behavior we know for the OS it is running on, so the module doubles
as a regression test for the assumptions the server makes. macOS-only behavior cannot be
probed on Windows/Linux; the README says so.

Run:  python main.py
"""

from __future__ import annotations

import ctypes
import os
import re
import socket
import subprocess
import sys
import time

import psutil

WIN = sys.platform == "win32"
MAC = sys.platform == "darwin"


def is_elevated() -> bool:
    if WIN:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())  # type: ignore[attr-defined]
    return os.geteuid() == 0


def quirk_visibility() -> None:
    """What can this account see? The answer differs per OS and per privilege."""
    print(f"1. platform={sys.platform} elevated={is_elevated()} psutil={psutil.__version__}")
    try:
        conns = psutil.net_connections(kind="inet")
        no_owner = sum(1 for c in conns if c.pid is None)
        print(f"   net_connections OK: {len(conns)} sockets, {no_owner} without a visible owner")
        if WIN or is_elevated():
            assert no_owner == 0 or WIN, "root/Windows should see owners"
    except psutil.AccessDenied:
        # macOS without root. The server then asks each process individually.
        assert MAC and not is_elevated(), "AccessDenied is only expected on unprivileged macOS"
        print("   net_connections raised AccessDenied (macOS, not root): per-process fallback")


def quirk_listener_state() -> None:
    """Does a fresh listening socket show up with status LISTEN? On some Windows 11 builds
    it shows as NONE, so 'status == LISTEN' alone would miss it."""
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    s.listen()
    port = s.getsockname()[1]
    try:
        mine = [c for c in psutil.net_connections(kind="tcp") if c.laddr and c.laddr.port == port]
        assert mine, "our own listening socket must be visible"
        status = mine[0].status
        print(f"2. status psutil reports for a plain listening socket: {status}")
        if WIN:
            assert status in (psutil.CONN_LISTEN, psutil.CONN_NONE)
        else:
            assert status == psutil.CONN_LISTEN
    finally:
        s.close()


def quirk_reuseaddr() -> None:
    """Why find_free_port never sets SO_REUSEADDR when probing."""
    first = socket.socket()
    first.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    first.bind(("127.0.0.1", 0))
    first.listen()
    port = first.getsockname()[1]
    second = socket.socket()
    second.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        second.bind(("127.0.0.1", port))
        stole = True
    except OSError:
        stole = False
    finally:
        second.close()
        first.close()
    print(f"3. second bind to a LISTENING port with SO_REUSEADDR succeeded: {stole}")
    # Windows: SO_REUSEADDR lets two sockets share an active port (port hijacking).
    # POSIX: it only relaxes TIME_WAIT; a live listener still blocks the second bind.
    assert stole == WIN


def quirk_terminate() -> None:
    """terminate() is polite on POSIX and brutal on Windows."""
    code = (
        "import signal, time\n"
        "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
        "print('ready', flush=True)\n"
        "time.sleep(600)\n"
    )
    p = subprocess.Popen([sys.executable, "-u", "-c", code], stdout=subprocess.PIPE, text=True)
    assert p.stdout is not None
    assert p.stdout.readline().strip() == "ready"
    try:
        ps = psutil.Process(p.pid)
        ps.terminate()
        time.sleep(1.0)
        survived = p.poll() is None
        print(f"4. process that ignores SIGTERM survived terminate(): {survived}")
        assert survived == (not WIN)
    finally:
        for c in psutil.Process(p.pid).children(recursive=True) if p.poll() is None else []:
            c.kill()
        p.kill()
        p.wait()
        p.stdout.close()


def quirk_excluded_ranges() -> None:
    """Windows reserves port ranges (Hyper-V, WSL, Docker). Nothing is listening there, but
    bind() fails with WSAEACCES (10013). find_free_port must skip them, hence the bind test."""
    if not WIN:
        print("5. (Windows-only: excluded port ranges; nothing to probe here)")
        return
    out = subprocess.run(
        ["netsh", "int", "ipv4", "show", "excludedportrange", "protocol=tcp"],
        capture_output=True,
        text=True,
    ).stdout
    ranges = [(int(a), int(b)) for a, b in re.findall(r"^\s*(\d+)\s+(\d+)\s*\*?\s*$", out, re.M)]
    if not ranges:
        print("5. this machine has no excluded port ranges")
        return
    low, high = ranges[0]
    s = socket.socket()
    try:
        s.bind(("127.0.0.1", low))
        raise AssertionError(f"bind inside excluded range {low}-{high} should fail")
    except OSError as e:
        print(f"5. {len(ranges)} excluded ranges; bind({low}) failed: WinError {e.winerror} with nothing listening")
        assert e.winerror == 10013
    finally:
        s.close()


def quirk_dual_stack() -> None:
    """One '::' socket serves IPv4 and IPv6. Windows lists it as TWO rows (0.0.0.0 and ::),
    Linux as one - so the server groups rows per process and port instead of trusting row counts."""
    if not socket.has_ipv6:
        print("6. (skipped: IPv6 unavailable)")
        return
    s = socket.socket(socket.AF_INET6)
    try:
        s.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
        s.bind(("::", 0))
        s.listen()
    except OSError as e:
        s.close()
        print(f"6. (skipped: cannot create a dual-stack socket here: {e})")
        return
    port = s.getsockname()[1]
    try:
        v4 = socket.create_connection(("127.0.0.1", port), timeout=5)
        v4.close()
        rows = [c for c in psutil.net_connections(kind="tcp") if c.laddr and c.laddr.port == port and not c.raddr]
        ips = {c.laddr.ip for c in rows}
        print(f"6. IPv4 client reached a '::' socket; listening rows for it: {sorted(ips)}")
        assert ips <= {"::", "0.0.0.0"} and ips
        if WIN:
            assert ips == {"::", "0.0.0.0"}
    finally:
        s.close()


if __name__ == "__main__":
    quirk_visibility()
    quirk_listener_state()
    quirk_reuseaddr()
    quirk_terminate()
    quirk_excluded_ranges()
    quirk_dual_stack()
    print("module 06 OK")
