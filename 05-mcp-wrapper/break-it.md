# Break It: The MCP Wrapper

## Challenge 1: Print to Stdout

Add `print("planning", port)` at the top of `kill_port` and run the demo. What does the client
do? Change it to `print(..., file=sys.stderr)`.

## Challenge 2: Lose the Message

Remove `Refused` from the `except` tuple in `tool()`. Run the demo's already-used-token step.
What does the model see now, and what could it possibly do about it?

## Challenge 3: Catch Everything

Change the `except` to `except Exception`. Everything "works" and the errors are all readable.
Add a deliberate typo (`pid_s` instead of `pids`) inside `whats_on_port`. What does the agent
see, and what would you have preferred?

**Hint:** Catching everything turns *your* bugs into confident-sounding advice to the user.

## Challenge 4: A Vague Docstring

Replace `kill_port`'s docstring with `"""Kill a port."""`. Ask a model (or read the schema as
one would) whether it is clear that nothing is killed on the first call. Why is the
instructions string in `MCPServer(...)` not enough on its own?

## Challenge 5: Hang the Agent

Call `check_port_reachable("10.255.255.1", 80, timeout=60)`. The call returns a long time later.
The full server clamps the timeout to 0.1-30 s. Where would you put the clamp here, and what
should it do when the value is out of range: silently adjust, or raise?
