# Break It: Cross-Platform Quirks

## Challenge 1: Probe With SO_REUSEADDR

Write a `bind_probe(port)` that sets `SO_REUSEADDR`. Point it at a port held by a live
listener. On Windows what does it say? On Linux or macOS (if you can run it)?

## Challenge 2: Trust "Not Listening"

Write `naive_free(port)` that returns `not any(c.laddr.port == port for c in
psutil.net_connections())`. On Windows, feed it the first port of an excluded range from
step 5. Then fix it so it also tries to bind.

## Challenge 3: Count Rows

Write a function that reports "N listening ports" by counting `net_connections()` rows. Run it
with a dual-stack `::` listener open. Is N the same on Windows and Linux? Make it count
distinct `(pid, port)` pairs instead.

## Challenge 4: Simulate macOS

You cannot trigger macOS's `AccessDenied` on another OS, but you can test the *fallback*:
write `scan_per_process()` that iterates `psutil.process_iter()` and calls
`p.net_connections()` for each, counting the processes that raise `AccessDenied`. Compare its
result for your own listener with the full-table version. What is different about the `pid`
field of the connections it returns?

**Hint:** `proc.net_connections()` returns connections without a `pid`, since the process is
already known. The fallback has to attach it.

## Challenge 5: Windows Sends No SIGTERM

On Linux or macOS, run the `quirk_terminate` experiment. On Windows, find a console program
that can shut down gracefully (for example by handling `CTRL_BREAK_EVENT` in a process group)
and think about what the server would need to do to offer it. Why is this not in the first
version?
