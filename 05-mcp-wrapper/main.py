"""Module 05: wrap the safe-kill core in an MCP server and talk to it over real stdio.

Two roles live in this file (same trick as the other course, one file, two modes):

  python main.py --serve [--ttl SECONDS]
      The MCP server. A client launches this as a subprocess and speaks JSON-RPC on stdio.
      NEVER print() in this mode: stdout is the protocol channel. Log to stderr.

  python main.py
      The demo: starts the server as a subprocess, connects as a client, lists the tools,
      and runs find -> plan -> confirm -> freed against a real http.server.
"""

from __future__ import annotations

# --- BEGIN KILL CORE ---
import secrets
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field

import psutil

HARD_PIDS = {0, 1, 4}  # idle/kernel, init, the Windows "System" process


class Refused(Exception):
    """Something the tool will not do. The message tells the agent why and what to do."""


def listener_pids(port: int) -> set[int]:
    """PIDs of processes with a TCP socket listening on ``port``."""
    pids: set[int] = set()
    for c in psutil.net_connections(kind="tcp"):
        if not c.laddr or c.laddr.port != port:
            continue
        # Some Windows 11 builds report a listener as state NONE with no remote end.
        listening = c.status == psutil.CONN_LISTEN or (
            sys.platform == "win32" and c.status == psutil.CONN_NONE and not c.raddr
        )
        if not listening:
            continue
        if c.pid is None:
            raise Refused(f"port {port} is held by a process the OS hides; run elevated")
        pids.add(c.pid)
    return pids


def protected_pids() -> set[int]:
    """This process and every ancestor (the MCP client, the terminal...)."""
    me = psutil.Process()
    return {me.pid, *(p.pid for p in me.parents())}


@dataclass
class Plan:
    token: str
    port: int
    expires_at: float
    victims: dict[int, float]  # pid -> create_time, to detect PID reuse
    text: str = ""


@dataclass
class PlanStore:
    ttl: float = 60.0
    clock: Callable[[], float] = time.monotonic  # injectable, so tests need no sleeping
    plans: dict[str, Plan] = field(default_factory=dict)

    def redeem(self, token: str, port: int) -> Plan:
        plan = self.plans.pop(token, None)  # pop: a token can only ever be used once
        if plan is None:
            raise Refused("unknown or already-used confirm_token; request a new plan")
        if self.clock() >= plan.expires_at:
            raise Refused("confirm_token expired; request a new plan")
        if plan.port != port:
            raise Refused(f"confirm_token was issued for port {plan.port}, not {port}")
        return plan


def make_plan(port: int, store: PlanStore) -> Plan:
    """Step 1. Decide what WOULD be killed. Kills nothing."""
    pids = listener_pids(port)
    if not pids:
        raise Refused(f"nothing is listening on port {port}")
    banned = protected_pids()
    victims: dict[int, float] = {}
    lines = [f"PLAN for port {port}: nothing has been killed yet"]
    for pid in sorted(pids):
        root = psutil.Process(pid)
        for p in [root, *root.children(recursive=True)]:  # the whole tree
            if p.pid in HARD_PIDS or p.pid in banned:
                raise Refused(f"PID {p.pid} ({p.name()}) is protected and can never be killed")
            victims[p.pid] = p.create_time()
            lines.append(f"  would stop PID {p.pid} {p.name()}")
    plan = Plan(secrets.token_hex(6), port, store.clock() + store.ttl, victims)
    lines.append(f"confirm with token {plan.token} (single use, {store.ttl:g} s)")
    plan.text = "\n".join(lines)
    store.plans[plan.token] = plan
    return plan


def _alive(p: psutil.Process) -> bool:
    try:
        return p.is_running() and p.status() != psutil.STATUS_ZOMBIE
    except psutil.NoSuchProcess:
        return False


def _wait_gone(procs: list[psutil.Process], timeout: float) -> list[psutil.Process]:
    end = time.monotonic() + timeout
    alive = [p for p in procs if _alive(p)]
    while alive and time.monotonic() < end:
        time.sleep(0.05)
        alive = [p for p in alive if _alive(p)]
    return alive


def execute(plan: Plan, grace: float = 3.0) -> str:
    """Step 2. Re-check the world, stop politely, escalate, then PROVE the port is free."""
    if not listener_pids(plan.port) <= set(plan.victims):
        raise Refused("ABORTED, nothing killed: a different process now holds the port")
    procs: list[psutil.Process] = []
    for pid, created in plan.victims.items():
        try:
            p = psutil.Process(pid)
        except psutil.NoSuchProcess:
            continue  # already gone
        if p.create_time() != created:
            raise Refused(f"ABORTED, nothing killed: PID {pid} was reused by another program")
        procs.append(p)
    for p in procs:
        try:
            p.terminate()  # SIGTERM on POSIX; TerminateProcess (immediate) on Windows
        except psutil.NoSuchProcess:
            pass
    stubborn = _wait_gone(procs, grace)
    for p in stubborn:
        try:
            p.kill()  # SIGKILL: cannot be ignored
        except psutil.NoSuchProcess:
            pass
    still = _wait_gone(stubborn, 5.0)
    deadline = time.monotonic() + 5.0
    while listener_pids(plan.port) and time.monotonic() < deadline:
        time.sleep(0.1)
    if still or listener_pids(plan.port):
        raise Refused(f"port {plan.port} is still in use after the kill (a supervisor?)")
    note = f" ({len(stubborn)} needed a force-kill)" if stubborn else ""
    return f"stopped {len(procs)} process(es){note}; port {plan.port} is free"
# --- END KILL CORE ---

# ---- the MCP layer ------------------------------------------------------------------------

import argparse  # noqa: E402
import asyncio  # noqa: E402
import functools  # noqa: E402
import re  # noqa: E402
import socket  # noqa: E402
import subprocess  # noqa: E402
from typing import Any, TypeVar  # noqa: E402

from mcp.server.mcpserver import MCPServer  # noqa: E402
from mcp.server.mcpserver.exceptions import ToolError  # noqa: E402

mcp = MCPServer(
    "ports-mini",
    instructions=(
        "Find what is using a TCP port and free it. Call kill_port(port) FIRST: it kills "
        "nothing and returns a plan with a confirm_token. Show the plan to the user; only "
        "after they agree call kill_port(port, confirm_token=...)."
    ),
)
store = PlanStore()
F = TypeVar("F", bound=Callable[..., Any])


def tool(fn: F) -> F:
    """Register ``fn`` as an MCP tool and turn our expected failures into ToolError.

    mcp>=2 sends the client ONLY the message of a ToolError. Any other exception reaches the
    agent as a bare "Error executing tool <name>", with the useful text hidden. So every
    failure the agent can act on (Refused, bad input) is converted here, at the boundary,
    and real bugs stay hidden on purpose.
    """

    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return fn(*args, **kwargs)
        except (Refused, ValueError, psutil.Error) as e:
            raise ToolError(str(e)) from e

    mcp.tool()(wrapper)
    return fn


def check_port(port: int) -> None:
    if not 1 <= port <= 65535:
        raise ValueError(f"port must be between 1 and 65535, got {port}")


@tool
def whats_on_port(port: int) -> str:
    """Say which process is listening on a TCP port: PID, name, command line, working
    directory and the address it is bound to. Use this before kill_port."""
    check_port(port)
    pids = listener_pids(port)
    if not pids:
        return f"Nothing is listening on tcp port {port}."
    out = []
    for pid in sorted(pids):
        p = psutil.Process(pid)
        out.append(f"PID {pid} {p.name()}\n  cmd: {' '.join(p.cmdline())}\n  cwd: {p.cwd()}")
    return "\n".join(out)


@tool
def kill_port(port: int, confirm_token: str | None = None) -> str:
    """Free a TCP port by stopping the process on it. TWO STEPS: calling without
    confirm_token only returns a plan (nothing is killed). Show it to the user; after they
    agree, call again with the confirm_token from the plan."""
    check_port(port)
    if confirm_token is None:
        return make_plan(port, store).text
    return execute(store.redeem(confirm_token, port), grace=2.0)


@tool
def check_port_reachable(host: str, port: int, timeout: float = 3.0) -> str:
    """Try a TCP connect to host:port and say REACHABLE or UNREACHABLE and why."""
    check_port(port)
    try:
        socket.create_connection((host, port), timeout=timeout).close()
    except ConnectionRefusedError:
        return f"UNREACHABLE: {host}:{port} refused the connection (nothing is listening)."
    except OSError as e:
        return f"UNREACHABLE: {host}:{port} failed ({e})."
    return f"REACHABLE: {host}:{port} accepted a connection."


@mcp.tool()
def demo_unwrapped_error() -> str:
    """Teaching only: raises Refused WITHOUT the ToolError wrapper, to show what an agent sees."""
    raise Refused("this useful explanation never reaches the agent")


# ---- demo client --------------------------------------------------------------------------


async def demo() -> None:
    from mcp import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client

    target = subprocess.Popen(
        [sys.executable, "-u", "-m", "http.server", "0", "--bind", "127.0.0.1"],
        stdout=subprocess.PIPE,
        text=True,
    )
    assert target.stdout is not None
    port = int(target.stdout.readline().split(" port ")[1].split()[0])
    params = StdioServerParameters(command=sys.executable, args=[__file__, "--serve"])
    try:
        async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
            init = await session.initialize()
            print(f"connected to server {init.server_info.name!r}")
            tools = (await session.list_tools()).tools
            for t in tools:
                print(f"  tool {t.name}: {t.input_schema.get('properties', {}).keys()}")
            assert {t.name for t in tools} >= {"whats_on_port", "kill_port", "check_port_reachable"}

            res = await session.call_tool("whats_on_port", {"port": port})
            print(res.content[0].text)  # type: ignore[union-attr]
            assert "http.server" in res.content[0].text  # type: ignore[union-attr]

            res = await session.call_tool("kill_port", {"port": port})
            plan = res.content[0].text  # type: ignore[union-attr]
            print(plan)
            token = re.search(r"token (\w+)", plan)
            assert token and "nothing has been killed yet" in plan

            res = await session.call_tool("kill_port", {"port": port, "confirm_token": token.group(1)})
            print(res.content[0].text)  # type: ignore[union-attr]
            assert not res.is_error and "is free" in res.content[0].text  # type: ignore[union-attr]

            # Errors: the wrapped one is instructive, the unwrapped one is useless.
            res = await session.call_tool("kill_port", {"port": port, "confirm_token": token.group(1)})
            print("wrapped error  ->", res.content[0].text)  # type: ignore[union-attr]
            assert res.is_error and "already-used" in res.content[0].text  # type: ignore[union-attr]
            res = await session.call_tool("demo_unwrapped_error", {})
            print("unwrapped error->", res.content[0].text)  # type: ignore[union-attr]
            assert res.is_error and "useful explanation" not in res.content[0].text  # type: ignore[union-attr]
    finally:
        try:
            for child in psutil.Process(target.pid).children(recursive=True):
                child.kill()
        except psutil.NoSuchProcess:
            pass
        target.kill()
        target.wait()
        target.stdout.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--serve", action="store_true")
    ap.add_argument("--ttl", type=float, default=60.0, help="confirm token lifetime in seconds")
    args = ap.parse_args()
    if args.serve:
        store.ttl = args.ttl
        mcp.run()
    else:
        asyncio.run(demo())
        print("module 05 OK")
