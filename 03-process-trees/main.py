"""Module 03: process trees, launcher shims and supervisors that respawn what you kill.

Run:  python main.py
"""

from __future__ import annotations

import subprocess
import sys
import time

import psutil

# A parent that listens on a port and owns one worker process.
PARENT = """
import socket, subprocess, sys, time
s = socket.socket(); s.bind(("127.0.0.1", 0)); s.listen()
worker = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(600)"])
print(s.getsockname()[1], worker.pid, flush=True)
time.sleep(600)
"""

# A supervisor: restarts its worker whenever it dies (think nodemon, a service manager).
SUPERVISOR = """
import subprocess, sys, time
while True:
    w = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(600)"])
    print(w.pid, flush=True)
    w.wait()
    time.sleep(0.1)
"""


def spawn(source: str) -> subprocess.Popen[str]:
    return subprocess.Popen([sys.executable, "-u", "-c", source], stdout=subprocess.PIPE, text=True)


def tree_lines(root_pid: int, mark: int | None = None) -> list[str]:
    """Render the process and all its descendants, indented by depth."""
    lines: list[str] = []

    def walk(p: psutil.Process, depth: int) -> None:
        tag = "  <== target" if p.pid == mark else ""
        lines.append(f"{'    ' * depth}{p.name()} ({p.pid}){tag}")
        for kid in sorted(p.children(), key=lambda k: k.pid):  # direct children only
            walk(kid, depth + 1)

    walk(psutil.Process(root_pid), 0)
    return lines


def alive(pid: int) -> bool:
    try:
        p = psutil.Process(pid)
        return p.is_running() and p.status() != psutil.STATUS_ZOMBIE
    except psutil.NoSuchProcess:
        return False


def wait_for(pred, timeout: float = 10.0) -> bool:  # type: ignore[no-untyped-def]
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if pred():
            return True
        time.sleep(0.05)
    return False


def kill_tree(pid: int) -> None:
    """Kill a process and everything below it. Snapshot the children FIRST: once the
    parent dies, its children are re-parented and you can no longer find them."""
    root = psutil.Process(pid)
    victims = [root, *root.children(recursive=True)]
    for p in victims:
        try:
            p.kill()
        except psutil.NoSuchProcess:
            pass
    psutil.wait_procs(victims, timeout=5)


def main() -> None:
    procs: list[subprocess.Popen[str]] = []
    try:
        # 1. Build a real tree and render it.
        parent = spawn(PARENT)
        procs.append(parent)
        assert parent.stdout is not None
        port_s, worker_s = parent.stdout.readline().split()
        port, worker = int(port_s), int(worker_s)
        print("1. the tree under the process we started:")
        text = tree_lines(parent.pid, mark=worker)
        print("\n".join("   " + line for line in text))
        assert any(f"({worker})" in line for line in text)

        # 2. Ancestors: who started whom. parents() runs from the immediate parent upward.
        chain = [p.name() for p in psutil.Process(worker).parents()]
        print(f"2. ancestors of the worker, nearest first: {chain[:4]} ...")
        assert psutil.Process(worker).parents()[0].pid in {parent.pid, *(c.pid for c in psutil.Process(parent.pid).children(recursive=True))}

        # 3. Identity is (pid, create_time). PIDs are recycled; the creation time is not.
        w = psutil.Process(worker)
        created = w.create_time()
        assert psutil.Process(worker).create_time() == created
        print(f"3. worker identity = ({worker}, {created:.3f})")

        # 4. Killing the tree must take the children too, or they live on, orphaned.
        everyone = [parent.pid, *(c.pid for c in psutil.Process(parent.pid).children(recursive=True))]
        kill_tree(parent.pid)
        assert wait_for(lambda: not any(alive(p) for p in everyone))
        print(f"4. kill_tree stopped {len(everyone)} process(es); port {port} released")

        # 5. A supervisor undoes a naive kill. Killing only the worker is not enough...
        sup = spawn(SUPERVISOR)
        procs.append(sup)
        assert sup.stdout is not None
        first = int(sup.stdout.readline())
        psutil.Process(first).kill()
        second = int(sup.stdout.readline())  # the supervisor started a replacement
        assert second != first and alive(second)
        print(f"5. killed worker {first}; supervisor immediately started worker {second}")

        # ...you have to stop the supervisor (the parent), together with its tree.
        sup_tree = [sup.pid, *(c.pid for c in psutil.Process(sup.pid).children(recursive=True))]
        kill_tree(sup.pid)
        assert wait_for(lambda: not any(alive(p) for p in sup_tree))
        time.sleep(0.5)
        assert not alive(second)
        print("6. killing the supervisor's whole tree ends it for good")
    finally:
        for p in procs:
            try:
                kill_tree(p.pid)
            except psutil.NoSuchProcess:
                pass
            p.wait()
            if p.stdout:
                p.stdout.close()


if __name__ == "__main__":
    main()
    print("module 03 OK")
