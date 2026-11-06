"""Run every module's main.py for real, the way CI does.

Each main.py asserts its own claims (real sockets, real processes, a real MCP stdio session),
so a chapter whose code drifts from what its README says fails here. Also checks that the kill
core shared by modules 04 and 05 is byte-identical, and that every module has its docs.

Usage: python verify.py            # all modules
       python verify.py 04 06      # just these
"""

from __future__ import annotations

import glob
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
BEGIN, END = "# --- BEGIN KILL CORE ---", "# --- END KILL CORE ---"


def core(path: str) -> str:
    text = open(path, encoding="utf-8").read()
    return text[text.index(BEGIN) : text.index(END) + len(END)]


def main() -> int:
    wanted = set(sys.argv[1:])
    modules = sorted(d for d in glob.glob(os.path.join(ROOT, "[0-9][0-9]-*")) if os.path.isdir(d))
    failures: list[str] = []

    for d in modules:
        name = os.path.basename(d)
        if wanted and name[:2] not in wanted:
            continue
        for doc in ("README.md", "break-it.md", "main.py"):
            if not os.path.isfile(os.path.join(d, doc)):
                failures.append(f"{name}: missing {doc}")
        start = time.monotonic()
        r = subprocess.run(
            [sys.executable, os.path.join(d, "main.py")],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=180,
        )
        ok = r.returncode == 0 and f"module {name[:2]} OK" in r.stdout
        print(f"{'PASS' if ok else 'FAIL'} {name} ({time.monotonic() - start:.1f}s)")
        if not ok:
            failures.append(name)
            print(r.stdout[-1500:])
            print(r.stderr[-1500:])

    if not wanted or {"04", "05"} <= wanted:
        same = core(os.path.join(ROOT, "04-safety-and-confirm-tokens", "main.py")) == core(
            os.path.join(ROOT, "05-mcp-wrapper", "main.py")
        )
        print(f"{'PASS' if same else 'FAIL'} kill core identical in modules 04 and 05")
        if not same:
            failures.append("kill core drift between 04 and 05")

    if failures:
        print("FAILED:", ", ".join(failures))
        return 1
    print("all good")
    return 0


if __name__ == "__main__":
    sys.exit(main())
