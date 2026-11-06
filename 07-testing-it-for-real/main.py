"""Module 07: testing a process-killing server without mocking a single process.

This file is a small test suite (plain asserts, no framework) that launches module 05's server
over real stdio and drives it against REAL listener processes: an http.server, a parent with
a child, and one that ignores SIGTERM. The same shapes are what ports-mcp's pytest suite uses.

Run:  python main.py
"""

from __future__ import annotations

import asyncio
import os
import re
import socket
import subprocess
import sys
import textwrap
import time
from collections.abc import Awaitable, Callable
from contextlib import AsyncExitStack, contextmanager
from typing import Iterator

import psutil
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

HERE = os.path.dirname(os.path.abspath(__file__))
SERVER = os.path.join(HERE, "..", "05-mcp-wrapper", "main.py")

# -- fixtures: real processes on OS-assigned ports ------------------------------------------

TREE = """
import socket, subprocess, sys, time
s = socket.socket(); s.bind(("127.0.0.1", 0)); s.listen()
child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(600)"])
print(s.getsockname()[1], child.pid, flush=True)
time.sleep(600)
"""

STUBBORN = """
import signal, socket, time
signal.signal(signal.SIGTERM, signal.SIG_IGN)
s = socket.socket(); s.bind(("127.0.0.1", 0)); s.listen()
print(s.getsockname()[1], 0, flush=True)
time.sleep(600)
"""


class Fixture:
    def __init__(self, proc: subprocess.Popen[str], port: int, extra: int) -> None:
        self.proc, self.port, self.extra = proc, port, extra

    def family(self) -> list[int]:
        """The Popen pid plus every descendant (Windows launchers add a layer)."""
        try:
            return [self.proc.pid, *(c.pid for c in psutil.Process(self.proc.pid).children(recursive=True))]
        except psutil.NoSuchProcess:
            return []


@contextmanager
def listener(source: str | None = None) -> Iterator[Fixture]:
    """Start a listener and ALWAYS kill its whole tree afterwards, even if a test fails."""
    if source is None:  # the real http.server
        cmd = [sys.executable, "-u", "-m", "http.server", "0", "--bind", "127.0.0.1"]
    else:
        cmd = [sys.executable, "-u", "-c", textwrap.dedent(source)]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, text=True)
    assert p.stdout is not None
    first = p.stdout.readline()  # the process prints only after it is listening: no sleeping
    if source is None:
        port, extra = int(first.split(" port ")[1].split()[0]), 0
    else:
        port, extra = (int(x) for x in first.split())
    fx = Fixture(p, port, extra)
    try:
        yield fx
    finally:
        for pid in fx.family():
            try:
                psutil.Process(pid).kill()
            except psutil.NoSuchProcess:
                pass
        p.wait()
        p.stdout.close()


def port_is_free(port: int) -> bool:
    """Ground truth, independent of the server: can a new listener bind it?"""
    s = socket.socket()
    try:
        s.bind(("127.0.0.1", port))
        return True
    except OSError:
        return False
    finally:
        s.close()


def wait_until(pred: Callable[[], bool], timeout: float = 10.0) -> bool:
    """Poll instead of sleeping a fixed time: fast when it works, patient when it is slow."""
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if pred():
            return True
        time.sleep(0.05)
    return False


# -- the client side -------------------------------------------------------------------------


async def call(s: ClientSession, name: str, **args: object) -> tuple[bool, str]:
    r = await s.call_tool(name, args)
    return bool(r.is_error), r.content[0].text  # type: ignore[union-attr]


def token_of(plan: str) -> str:
    m = re.search(r"token (\w+)", plan)
    assert m, plan
    return m.group(1)


# -- the tests -------------------------------------------------------------------------------


async def t_discover_and_kill(s: ClientSession) -> None:
    with listener() as fx:
        err, text = await call(s, "whats_on_port", port=fx.port)
        assert not err and "http.server" in text
        _, plan = await call(s, "kill_port", port=fx.port)
        assert not port_is_free(fx.port), "planning must not kill anything"
        err, result = await call(s, "kill_port", port=fx.port, confirm_token=token_of(plan))
        assert not err and "is free" in result
        assert wait_until(lambda: port_is_free(fx.port))


async def t_tree_dies_together(s: ClientSession) -> None:
    with listener(TREE) as fx:
        family = fx.family()
        assert fx.extra in family
        _, plan = await call(s, "kill_port", port=fx.port)
        assert f"PID {fx.extra}" in plan, "the child must be in the plan"
        await call(s, "kill_port", port=fx.port, confirm_token=token_of(plan))
        assert wait_until(lambda: not any(psutil.pid_exists(p) and psutil.Process(p).status() != psutil.STATUS_ZOMBIE for p in family))


async def t_sigterm_ignorer_still_freed(s: ClientSession) -> None:
    with listener(STUBBORN) as fx:
        _, plan = await call(s, "kill_port", port=fx.port)
        err, result = await call(s, "kill_port", port=fx.port, confirm_token=token_of(plan))
        assert not err, result
        assert wait_until(lambda: port_is_free(fx.port))
        if sys.platform != "win32":
            assert "force-kill" in result


async def t_wrong_port_and_reuse_rejected(s: ClientSession) -> None:
    with listener() as a, listener() as b:
        _, plan = await call(s, "kill_port", port=a.port)
        err, msg = await call(s, "kill_port", port=b.port, confirm_token=token_of(plan))
        assert err and "issued for port" in msg
        assert not port_is_free(a.port) and not port_is_free(b.port)
        err, msg = await call(s, "kill_port", port=a.port, confirm_token=token_of(plan))
        assert err and "already-used" in msg  # burned by the wrong-port attempt


async def t_unknown_token_rejected(s: ClientSession) -> None:
    with listener() as fx:
        err, msg = await call(s, "kill_port", port=fx.port, confirm_token="0123456789ab")
        assert err and "unknown or already-used" in msg
        assert not port_is_free(fx.port)


async def t_refuses_to_kill_the_server_itself(s: ClientSession) -> None:
    # The MCP server's own parent is THIS process. Listen here and ask it to kill us.
    me = socket.socket()
    me.bind(("127.0.0.1", 0))
    me.listen()
    try:
        err, msg = await call(s, "kill_port", port=me.getsockname()[1])
        assert err and "protected" in msg, msg
    finally:
        me.close()


async def t_expired_token_rejected() -> None:
    # Time is the one thing worth controlling: start a second server whose tokens live 1 s.
    params = StdioServerParameters(command=sys.executable, args=[SERVER, "--serve", "--ttl", "1"])
    async with stdio_client(params) as (r, w), ClientSession(r, w) as s:
        await s.initialize()
        with listener() as fx:
            _, plan = await call(s, "kill_port", port=fx.port)
            await asyncio.sleep(1.5)
            err, msg = await call(s, "kill_port", port=fx.port, confirm_token=token_of(plan))
            assert err and "expired" in msg
            assert not port_is_free(fx.port)


TESTS: list[Callable[[ClientSession], Awaitable[None]]] = [
    t_discover_and_kill,
    t_tree_dies_together,
    t_sigterm_ignorer_still_freed,
    t_wrong_port_and_reuse_rejected,
    t_unknown_token_rejected,
    t_refuses_to_kill_the_server_itself,
]


async def main() -> None:
    params = StdioServerParameters(command=sys.executable, args=[SERVER, "--serve"])
    async with AsyncExitStack() as stack:
        r, w = await stack.enter_async_context(stdio_client(params))
        s = await stack.enter_async_context(ClientSession(r, w))
        await s.initialize()
        for t in TESTS:
            await t(s)
            print(f"PASS {t.__name__}")
    await t_expired_token_rejected()
    print("PASS t_expired_token_rejected")
    print(f"{len(TESTS) + 1} tests passed")


if __name__ == "__main__":
    asyncio.run(main())
    print("module 07 OK")
