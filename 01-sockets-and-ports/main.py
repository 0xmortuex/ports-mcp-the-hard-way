"""Module 01: what a port actually is, with nothing but the standard library.

Run:  python main.py        (exits 0 when every claim in the README holds on this machine)
"""

from __future__ import annotations

import errno
import ipaddress
import socket


def exposure(address: str) -> str:
    """Classify a bind address: who can reach a socket bound to it?"""
    ip = ipaddress.ip_address(address.split("%", 1)[0])  # drop a zone id like fe80::1%eth0
    if ip.is_unspecified:  # 0.0.0.0 or ::
        return "all interfaces"
    if ip.is_loopback:  # 127.0.0.0/8 or ::1
        return "loopback only"
    return "one interface"


def lan_address() -> str | None:
    """The address other machines would use to reach us, or None when offline.

    A UDP "connect" sends no packet; it only makes the OS pick the outgoing interface.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 9))
        return str(s.getsockname()[0])
    except OSError:
        return None
    finally:
        s.close()


def can_connect(host: str, port: int) -> bool:
    # 5 s, not 2: Windows retries a refused loopback SYN for about 2 seconds before it
    # reports ConnectionRefusedError, so a short timeout looks like a firewall drop.
    try:
        socket.create_connection((host, port), timeout=5).close()
        return True
    except OSError:
        return False


def main() -> None:
    # 1. Port 0 means "OS, pick a free one". This is how every test in this course avoids
    #    hard-coded ports that might already be taken.
    a = socket.socket()
    a.bind(("127.0.0.1", 0))
    a.listen()
    port = a.getsockname()[1]
    print(f"1. bind(port 0) gave us port {port}")
    assert 1024 <= port <= 65535

    # 2. Once listen() has been called, connections succeed even before accept().
    assert can_connect("127.0.0.1", port)
    print("2. a client can connect to the listening socket")

    # 3. A port belongs to exactly one listener per address: a second bind fails.
    b = socket.socket()
    try:
        b.bind(("127.0.0.1", port))
        raise AssertionError("second bind to a busy port must fail")
    except OSError as e:
        # Windows reports WSAEADDRINUSE (10048); POSIX reports EADDRINUSE.
        assert e.errno in (errno.EADDRINUSE, 10048), e
        print(f"3. second bind failed as expected: [{e.errno}] {e.strerror}")
    finally:
        b.close()

    # 4. Closing the listener frees the port: connections are now refused (nothing there).
    a.close()
    assert not can_connect("127.0.0.1", port)
    try:
        socket.create_connection(("127.0.0.1", port), timeout=5)
        raise AssertionError("connect to a closed port must fail")
    except ConnectionRefusedError:
        print("4. after close(), connect() raises ConnectionRefusedError: host up, nobody home")

    # 5. The bind address decides who can reach you.
    for addr in ("0.0.0.0", "127.0.0.1", "::", "::1", "192.168.1.20", "fe80::1%eth0"):
        print(f"5. {addr:<14} -> {exposure(addr)}")
    assert exposure("0.0.0.0") == "all interfaces"
    assert exposure("127.0.0.1") == "loopback only"
    assert exposure("::1") == "loopback only"
    assert exposure("192.168.1.20") == "one interface"

    lan = lan_address()
    if lan is None:
        print("6. (skipped: no network interface to test exposure against)")
        return
    wide = socket.socket()
    wide.bind(("0.0.0.0", 0))
    wide.listen()
    local = socket.socket()
    local.bind(("127.0.0.1", 0))
    local.listen()
    try:
        reach_wide = can_connect(lan, wide.getsockname()[1])
        reach_local = can_connect(lan, local.getsockname()[1])
        print(f"6. via LAN address {lan}: 0.0.0.0 listener reachable={reach_wide}, "
              f"127.0.0.1 listener reachable={reach_local}")
        assert reach_wide and not reach_local
    finally:
        wide.close()
        local.close()


if __name__ == "__main__":
    main()
    print("module 01 OK")
