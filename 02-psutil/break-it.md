# Break It: psutil

## Challenge 1: Trust Only LISTEN

In `is_listener`, delete the Windows `NONE` clause. On a Windows machine that behaves like
the author's, what does step 1 report? If your Windows prints `LISTEN` for your own sockets,
find out which: print `c.status` for the listener.

**Hint:** Compare with what `netstat -ano | findstr :PORT` shows. A tool that trusts only one
source can be confidently wrong.

## Challenge 2: Swallow AccessDenied

Change `describe()` so `AccessDenied` is caught and ignored (`pass`). Run step 4. What does
the output claim about PID 0 and other protected processes, and why is that worse than a crash?

## Challenge 3: A Process That Vanishes

Between `net_connections()` and `describe()` a process can exit. Call `describe(99999999)`.
What does it return, and what would happen in `main()` if it raised instead? Why is
`NoSuchProcess` handled but `AccessDenied` recorded?

**Hint:** "Gone" means there is nothing to report. "Denied" means there is something
you cannot see.

## Challenge 4: Count the Cost

Time `psutil.net_connections()` once. Then time `psutil.Process(pid).name()`,
`.cmdline()` and `.cwd()` separately, versus once inside `with p.oneshot():`. On Windows,
which one dominates, and why does `describe()` use `oneshot()`?
