# Module 07: Testing It For Real

## The Concept

A server that kills processes is the worst possible thing to test with mocks. A mocked
`psutil.Process` will happily "terminate" a fake, and will never reveal that the launcher PID is not
the listener PID, that a zombie still looks alive, that Windows reports state `NONE`, or that the
port is still held after the process "died". Every one of those was found in this project by
running the real thing. So:

> Start real processes on real ports. Ask the real server. Check the real port.

`main.py` is a small test suite that launches Module 05's server over stdio and drives it
against real listener processes. The full ports-mcp repo uses pytest with the same shapes.

## Fixtures: Real Processes on Random Ports

```python
with listener() as fx:       # python -m http.server 0   (the real thing)
    ... fx.port ...
```

- **Port 0.** The child binds an OS-assigned port and *prints it*; the test reads that line.
  No race between "find a free port" and "use it", no collisions between parallel runs.
- **Readiness without sleeping.** The child prints only *after* `listen()`. Reading that line
  blocks until the server is ready, so there is no `time.sleep(2)` that is too short on a slow
  CI box and too long everywhere else.
- **Always clean up.** The context manager kills the whole family (the process and its
  descendants) in `finally`. A failing test must not leave listeners behind to poison the next
  one. Descendants matter because on Windows the `Popen` object is a launcher.
- **Different shapes.** `TREE` (parent with a child), `STUBBORN` (ignores SIGTERM) and the plain
  `http.server`. Each exercises a branch of the kill logic that a single happy-path
  listener would not.

## Assert on Ground Truth

After a kill, don't believe the server's "port is free"; check it yourself:

```python
def port_is_free(port): ...   # try bind() it
assert wait_until(lambda: port_is_free(fx.port))
```

`wait_until` polls with a deadline. It returns as soon as the condition holds, and fails after
10 seconds, so the suite is fast when things work and still tolerant of a busy machine.

## What The Suite Covers

| Test | What it proves |
|------|----------------|
| `t_discover_and_kill` | `whats_on_port` sees it; **planning kills nothing**; confirm frees the port |
| `t_tree_dies_together` | the child is named in the plan and dies with its parent |
| `t_sigterm_ignorer_still_freed` | escalation works; on POSIX the result says "force-kill" |
| `t_wrong_port_and_reuse_rejected` | token for port A can't kill port B; both processes survive; the token is burned |
| `t_unknown_token_rejected` | an invented token does nothing |
| `t_refuses_to_kill_the_server_itself` | the server's parent (this test process) is protected |
| `t_expired_token_rejected` | token older than `--ttl` is rejected, process survives |

Notice the pattern in the negative tests: assert the **error**, *and* assert the process is still
listening. A rejection that also killed the process would pass a naive test.

## Make Time and Environment Injectable

Expiry is the one thing that needs time. Module 04 injected a clock into `PlanStore`; across a
process boundary the equivalent is a flag: `--ttl 1` starts a server whose tokens live one second.
Design for testing at the seams where it's cheap: a flag, a constructor argument, an environment
variable.

## What You Can't Test From One Machine

Be explicit about the gaps. This suite cannot show macOS behavior, Linux without root, or
Windows service processes being refused unless one happens to be listening. The full project
handles that by (a) unit tests on the pure decision functions (`soft_reasons` with a
constructed `svchost.exe`), (b) tests that run a *real* check when the situation exists on the
machine and skip with a reason when it doesn't, and (c) a three-OS CI matrix.

## Run It

```bash
python 07-testing-it-for-real/main.py
```

Or run the whole course:

```bash
python verify.py
```

## You Built It

You now have, in a few hundred lines, the core of [ports-mcp](https://github.com/0xmortuex/ports-mcp):
discovery with psutil, tree-aware planning, token-gated execution with escalation and
verification, an MCP wrapper with agent-readable errors, and tests that use real processes.
The full server adds UDP, framework detection, exposure flags, system-service classification,
free-port search and the per-OS fallbacks from Module 06.
