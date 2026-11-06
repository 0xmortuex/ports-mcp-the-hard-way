# Module 03: Process Trees

## The Concept

Every process has one parent and any number of children. Real dev servers are trees:

```
npm run dev
└── node vite.js          <-- holds port 5173
    └── esbuild --service
```

and on Windows even a plain `python script.py` from a virtualenv is two processes, a launcher
and the interpreter it starts (the demo's tree shows four layers because `PARENT` and its worker
are each launched that way). Free a port by killing "the PID on the port" and one of three
things happens: children are orphaned and keep running, a parent restarts the process, or both.

## Reading a Tree

```python
root = psutil.Process(pid)
root.children()                 # direct children
root.children(recursive=True)   # all descendants
root.parents()                  # ancestors, nearest first
```

`tree_lines()` renders it with indentation and marks the target. This is the same output the
server's `process_tree` tool returns, and what the kill plan uses to say *exactly* what will die.

## Identity: PID Plus Creation Time

PIDs are recycled. If you plan to kill PID 4412 and, ten seconds later when the user
confirms, PID 4412 is a different program, a PID-only kill is a bug with real consequences.
The fix is to treat identity as the pair `(pid, create_time)`:

```python
created = psutil.Process(pid).create_time()
# ... later ...
if psutil.Process(pid).create_time() != created: abort
```

Module 04 stores creation times in the plan and compares them again at execution.

## Snapshot Before You Strike

`kill_tree()` collects the descendants *before* killing anything. Once a parent dies, its
children are re-parented (to init on POSIX) and `children()` can no longer find them. Collect
first, then kill, then wait for all of them.

## Supervisors Undo Your Kill

Step 5 runs a tiny supervisor that restarts its worker whenever it exits, which is what
`nodemon`, process managers and service wrappers do. Kill only the worker and a replacement
appears 100 ms later with a new PID. That is also what the full server's final check catches:
after killing, it re-scans the port, and if something is listening again it says "a supervisor
or parent probably restarted it" and points at `process_tree`. The plan also names the parent
and says it is NOT being killed.

The right move is to stop the *parent* and its whole tree. The tool does not do that
automatically, because the parent might be your terminal, your editor or a service manager.
Deciding that is a human call, so the plan puts the information in front of the human.

## Run It

```bash
python 03-process-trees/main.py
```

## What's Missing

We can find a process, describe it and walk its tree. Killing it safely is a design problem,
not a one-liner. That is Module 04.

→ [Next: Module 04: Safety and Confirm Tokens](../04-safety-and-confirm-tokens/README.md)
