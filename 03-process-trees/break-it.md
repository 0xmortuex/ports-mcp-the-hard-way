# Break It: Process Trees

## Challenge 1: Kill the Parent First

In `kill_tree`, kill only `root` and skip the descendants. Run the module. Are the worker
processes still alive afterwards? Find them by hand with `psutil.process_iter()`. Which
process are they now children of?

**Hint:** On POSIX, orphans are adopted by init (PID 1); on Windows their `ppid` points at a
process that no longer exists. Either way nothing cleans them up.

## Challenge 2: Collect Children After the Kill

Reorder `kill_tree` so `children(recursive=True)` runs after `root.kill()`. What does it return?

## Challenge 3: Fool a PID-Only Check

Write a script that reads a PID from a process you started, kills it, and keeps spawning
short-lived processes until one gets the same PID (Windows reuses PIDs aggressively; Linux
needs the counter to wrap). Then show that comparing `create_time()` catches it.

## Challenge 4: Out-Smart the Supervisor

In step 5, change the supervisor's `time.sleep(0.1)` to `time.sleep(5)`. Is "kill the
worker, then check the port" still enough to notice the respawn? What does that tell you about
verifying a kill?

**Hint:** The check has to wait. The server polls the port for up to five seconds
before declaring success, but a supervisor with a longer delay would still slip past it, which
is why the plan shows the parent.
