# Break It: Safety and Confirm Tokens

## Challenge 1: Remove `pop`

In `PlanStore.redeem`, replace `self.plans.pop(token, None)` with `self.plans.get(token)`.
Which scenario now passes when it should fail? Write the failing assertion first.

**Hint:** Tokens must be consumed at lookup time, before any check that might raise.

## Challenge 2: Kill Your Own Parent

Create a listener, then, from a child process, call `make_plan` on the parent's port. The
refusal comes from `protected_pids()`. Remove the `me.parents()` half and confirm the plan
is now created. Why would that be catastrophic when the parent is Claude Desktop?

## Challenge 3: Skip the Re-Check

Delete the `create_time` comparison in `execute`. Describe, step by step, a sequence of events
in which approving a plan kills a program the user never saw. How likely is it on a busy
machine? On Windows?

## Challenge 4: Declare Victory Early

Remove the final `listener_pids` check, so `execute` returns success after sending signals.
Start a supervisor from Module 03 on a port and kill it. What does the agent now believe, and
what is actually true?

## Challenge 5: Add a Dry-Run Lie

Make `make_plan` list only the root process and not its children. Everything still "works".
What breaks for the user, and why is the plan's accuracy part of the safety design rather than
a courtesy?
