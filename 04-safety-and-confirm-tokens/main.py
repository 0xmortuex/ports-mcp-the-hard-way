"""Module 04: a kill an agent cannot trigger by accident - plan, token, re-check, escalate.

Run:  python main.py
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


# ---- demo helpers (not part of the core) -------------------------------------------------

import subprocess  # noqa: E402

LISTENER = """
import signal, socket, sys, time
if "ignore-term" in sys.argv:
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
s = socket.socket(); s.bind(("127.0.0.1", 0)); s.listen()
print(s.getsockname()[1], flush=True)
time.sleep(600)
"""


def spawn(*flags: str) -> tuple[subprocess.Popen[str], int]:
    p = subprocess.Popen(
        [sys.executable, "-u", "-c", LISTENER, *flags], stdout=subprocess.PIPE, text=True
    )
    assert p.stdout is not None
    return p, int(p.stdout.readline())


def port_free(port: int) -> bool:
    return not listener_pids(port)


def expect_refused(fn: Callable[[], object], fragment: str) -> None:
    try:
        fn()
    except Refused as e:
        assert fragment in str(e), f"wanted {fragment!r} in {e}"
        print(f"   refused: {e}")
        return
    raise AssertionError(f"expected a refusal containing {fragment!r}")


def main() -> None:
    procs: list[subprocess.Popen[str]] = []
    try:
        store = PlanStore()

        print("1. the plan alone kills nothing")
        p1, port1 = spawn()
        procs.append(p1)
        plan = make_plan(port1, store)
        print("   " + plan.text.replace("\n", "\n   "))
        assert not port_free(port1)

        print("2. a token for another port is rejected (and burned)")
        p2, port2 = spawn()
        procs.append(p2)
        expect_refused(lambda: store.redeem(plan.token, port2), "issued for port")
        expect_refused(lambda: store.redeem(plan.token, port1), "unknown or already-used")
        assert not port_free(port1) and not port_free(port2)

        print("3. an expired token is rejected (fake clock, no sleeping)")
        now = [100.0]
        fast = PlanStore(ttl=60.0, clock=lambda: now[0])
        stale = make_plan(port2, fast)
        now[0] += 61
        expect_refused(lambda: fast.redeem(stale.token, port2), "expired")
        assert not port_free(port2)

        print("4. plan -> confirm -> the port is really free")
        plan = make_plan(port1, store)
        print("   " + execute(store.redeem(plan.token, port1)))
        assert port_free(port1)
        expect_refused(lambda: store.redeem(plan.token, port1), "already-used")  # single use

        print("5. a process that ignores SIGTERM is escalated to a force-kill")
        p3, port3 = spawn("ignore-term")
        procs.append(p3)
        result = execute(store.redeem(make_plan(port3, store).token, port3), grace=1.0)
        print("   " + result)
        assert port_free(port3)
        if sys.platform != "win32":
            assert "force-kill" in result
        else:
            print("   (Windows has no ignorable SIGTERM: terminate() is already a hard kill)")

        print("6. we refuse to kill ourselves")
        import socket

        me = socket.socket()
        me.bind(("127.0.0.1", 0))
        me.listen()
        try:
            expect_refused(lambda: make_plan(me.getsockname()[1], store), "protected")
        finally:
            me.close()

        print("7. nothing there -> a clear message, not a crash")
        expect_refused(lambda: make_plan(port1, store), "nothing is listening")
        port2_plan = make_plan(port2, store)  # leave p2 for cleanup below
        assert port2_plan.victims
    finally:
        for p in procs:
            try:  # on Windows the Popen is a launcher; the listener is its child
                for child in psutil.Process(p.pid).children(recursive=True):
                    child.kill()
            except psutil.NoSuchProcess:
                pass
            p.kill()
            p.wait()
            if p.stdout:
                p.stdout.close()


if __name__ == "__main__":
    main()
    print("module 04 OK")
