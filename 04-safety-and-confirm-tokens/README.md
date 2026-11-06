# Module 04: Safety Design and Confirm Tokens

## The Concept

A tool that kills processes, called by a language model, is a loaded gun with a friendly
interface. The model may be wrong about which port the user meant, may be steered by text
inside a web page it read, or may simply be in a hurry. The design goal: **a mistake costs one
extra message, never a lost database.**

Nothing here is specific to ports. It is a pattern for any destructive tool.

## Pattern 1: Plan, Then Confirm

`kill_port(port)` does not kill. It returns a *plan*: every process (children included) that
would die, and a token. Only `kill_port(port, confirm_token=...)` acts.

```
PLAN for port 54305: nothing has been killed yet
  would stop PID 8816 python.exe
confirm with token 3fc9f6425b4f (single use, 60 s)
```

The plan is written for the human behind the model. The system prompt of the full server tells the
model to show it and wait for agreement. A prompt is not a guarantee, which is why the token has
rules a model cannot talk its way around:

| Rule | Why | Code |
|------|-----|------|
| Random (`secrets.token_hex`) | cannot be guessed or invented | `make_plan` |
| Single use (`dict.pop`) | an old approval cannot be replayed | `redeem` |
| Expires (60 s) | approval of a stale situation is not approval | `redeem` |
| Bound to a port | approval for port 3000 is not approval for port 5432 | `redeem` |

A rejected wrong-port token is *burned*, not kept. A confused call is a signal to start over.

## Pattern 2: Re-Check at Execution

Between plan and confirm, the world moves. `execute()` therefore verifies again:

- the listeners on the port are still within the planned set, otherwise a different program has
  the port now and the human approved something else (`ABORTED, nothing killed`);
- each process has the same `create_time` it had in the plan, otherwise the PID was reused.

## Pattern 3: Refuse Rather Than Warn

Some requests should fail even with the right token:

- PIDs `0`, `1`, `4`: idle/kernel, init, the Windows `System` process;
- this server's own PID and all its ancestors. The parent chain contains your MCP client and
  terminal. Killing it would end the very conversation asking for the kill.

The full server adds a middle tier: operating-system services (`svchost`, `systemd`, processes
running as SYSTEM, Docker Desktop's backend) are refused *unless* the planning call passes
`force=True`, and even then a plan and confirmation are required. Two levels, because "never"
and "not without saying you mean it" are different promises.

## Pattern 4: Escalate, Then Prove

```python
p.terminate()                 # ask: SIGTERM on POSIX
stubborn = _wait_gone(procs, grace)
for p in stubborn: p.kill()   # insist: SIGKILL, which cannot be ignored
...
if listener_pids(port): raise Refused("port is still in use")
```

Graceful first lets servers flush files and close connections. A process that ignores SIGTERM
(the demo has one) is force-killed after `grace` seconds, and the result says so.
On Windows `terminate()` is already `TerminateProcess`, an immediate hard kill with no
catchable signal, so there is no polite step and the tool says that in the plan text.

The last lines matter most: success means *the port is free*, not "the signals were sent".
A supervisor that restarted the process makes the tool report failure and tell the agent where
to look.

## Time Is Injectable

`PlanStore(clock=...)` takes the clock as a parameter. The demo's expiry test sets
`now[0] += 61` instead of sleeping, so the test is instant and exact. Anything that depends on
time should get its clock this way.

## Run It

```bash
python 04-safety-and-confirm-tokens/main.py
```

Seven scenarios against real listener processes: plan kills nothing, wrong-port token, expired
token, full plan-confirm-freed flow, a SIGTERM-ignoring process, self-protection, and nothing
listening.

The code between `BEGIN KILL CORE` and `END KILL CORE` is copied verbatim into Module 05;
`verify.py` checks the two copies are identical.

## What's Missing

The logic works but only a Python caller can use it. Module 05 puts it behind MCP.

→ [Next: Module 05: The MCP Wrapper](../05-mcp-wrapper/README.md)
