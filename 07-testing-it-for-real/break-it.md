# Break It: Testing It For Real

## Challenge 1: Sleep Instead of Read

In `listener()`, replace `p.stdout.readline()` with `time.sleep(0.2)` and a hard-coded port.
Run the suite ten times. Which failures appear, and why are they intermittent?

## Challenge 2: Leak a Listener

Remove the `finally` cleanup in `listener()` and make one assertion fail on purpose. Run the
suite again. What breaks in the tests that come *after* the failing one?

## Challenge 3: Break the Server and Watch Tests Catch It

Pick one in `05-mcp-wrapper/main.py` and break it, one at a time, then run module 07:
1. `self.plans.pop(token, None)` becomes `.get(token)`
2. delete the `plan.port != port` check
3. delete the `create_time` re-check (which tests catch it? if none, write one)
4. make `make_plan` kill immediately

For each, note which test failed first. A safety check no test notices is a safety check you do
not have.

## Challenge 4: Add the Missing Test

Write `t_udp_port` or `t_supervisor_respawn`: start Module 03's supervisor behind a listener,
kill through the tool, and assert on what the server says when the port comes back. Decide what
the *right* message is first.

## Challenge 5: Test the Stale Plan

Plan a kill, stop the listener yourself, start a different listener on the same port number if
you can get the OS to allow it, then confirm. Which line of `execute()` protects you? Why is this
hard to test, and what would you inject to make it easy?
