"""Module 02: from "something is on port N" to "this process, started like this, in that folder".

Run:  python main.py
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass, field

import psutil


@dataclass
class Listener:
    port: int
    address: str
    pid: int | None  # None: the OS would not tell us who owns the socket


def is_listener(c) -> bool:  # type: ignore[no-untyped-def]
    """True for a TCP socket that accepts connections."""
    if not c.laddr or c.type != 1:  # 1 == SOCK_STREAM
        return False
    if c.status == psutil.CONN_LISTEN:
        return True
    # Some Windows 11 builds report listening sockets created in restricted contexts as
    # state NONE (and netstat omits them). No remote end + NONE means listener there.
    return sys.platform == "win32" and c.status == psutil.CONN_NONE and not c.raddr


def listeners() -> list[Listener]:
    out = [
        Listener(c.laddr.port, c.laddr.ip, c.pid)
        for c in psutil.net_connections(kind="inet")
        if is_listener(c)
    ]
    return sorted(out, key=lambda ln: ln.port)


@dataclass
class Info:
    pid: int
    name: str | None = None
    cmdline: list[str] | None = None
    cwd: str | None = None
    denied: list[str] = field(default_factory=list)  # what the OS refused to tell us


def describe(pid: int) -> Info | None:
    """Everything we may see about a process. None if it is gone.

    AccessDenied is NOT an error to swallow and it is NOT "empty": it is a fact the user
    needs ("run elevated to see this"), so it is recorded by field name.
    """
    info = Info(pid)
    try:
        p = psutil.Process(pid)
        with p.oneshot():  # one OS query instead of one per attribute
            for attr in ("name", "cmdline", "cwd"):
                try:
                    setattr(info, attr, getattr(p, attr)())
                except psutil.AccessDenied:
                    info.denied.append(attr)
    except psutil.NoSuchProcess:
        return None
    return info


def start_http_server() -> tuple[subprocess.Popen[str], int]:
    """A real server on an OS-assigned port. -u: unbuffered, so we can read its banner."""
    p = subprocess.Popen(
        [sys.executable, "-u", "-m", "http.server", "0", "--bind", "127.0.0.1"],
        stdout=subprocess.PIPE,
        text=True,
    )
    assert p.stdout is not None
    banner = p.stdout.readline()  # "Serving HTTP on 127.0.0.1 port 54321 (...)"
    return p, int(banner.split(" port ")[1].split()[0])


def main() -> None:
    server, port = start_http_server()
    try:
        # 1. The whole question "what is on port N?" is a filter over one psutil call.
        mine = [ln for ln in listeners() if ln.port == port]
        print(f"1. listeners on {port}: {mine}")
        assert mine and mine[0].address == "127.0.0.1" and mine[0].pid is not None

        # 2. Then ask the owner who it is.
        info = describe(mine[0].pid)
        assert info is not None
        print(f"2. name={info.name} cwd={info.cwd}")
        print(f"   cmdline={info.cmdline}")
        assert info.cmdline and "http.server" in info.cmdline
        assert info.cwd

        # 3. On Windows the pid we found may not be the pid we spawned: a venv's python.exe
        #    is a launcher that starts the real interpreter as a child. Ask psutil.
        spawned_family = {server.pid} | {c.pid for c in psutil.Process(server.pid).children(recursive=True)}
        assert mine[0].pid in spawned_family
        print(f"3. spawned pid {server.pid}; listener pid {mine[0].pid}; family {sorted(spawned_family)}")

        # 4. AccessDenied is normal. Count how many processes on this machine hide details
        #    from us, and show that describe() reports it instead of crashing or lying.
        hidden = [i for p in psutil.process_iter() if (i := describe(p.pid)) and i.denied]
        print(f"4. {len(hidden)} process(es) hide details from this user", end="")
        if hidden:
            h = hidden[0]
            print(f", e.g. PID {h.pid} {h.name!r} denied {h.denied}")
            assert all(d in ("name", "cmdline", "cwd") for d in h.denied)
        else:
            print(" (this account can see everything, e.g. you are root/admin)")

        # 5. Sockets whose owner is hidden show up with pid=None. Linux does this for other
        #    users' sockets when you are not root.
        unknown = [ln for ln in listeners() if ln.pid is None]
        print(f"5. listeners with an unidentified owner: {len(unknown)}")
    finally:
        server.kill()
        server.wait()
        if server.stdout:
            server.stdout.close()

    # 6. After the process is gone, so is the listener.
    assert not [ln for ln in listeners() if ln.port == port]
    print("6. port is free again")


if __name__ == "__main__":
    main()
    print("module 02 OK")
