# Module 05: The MCP Wrapper

## The Concept

MCP is JSON-RPC over a pipe. The client (Claude Desktop, Claude Code) launches your server as
a subprocess, writes requests to its stdin and reads responses from its stdout. Three requests
matter: `initialize` (handshake), `tools/list` (what can you do?) and `tools/call`.

With the `mcp` SDK, a tool is a function:

```python
@mcp.tool()
def whats_on_port(port: int) -> str:
    """Say which process is listening on a TCP port ..."""
```

The type hints become the JSON schema of the arguments; the **docstring becomes the
description the model reads when deciding what to call**. Write it for a model: when to use
the tool, what it returns, what to do next. For `kill_port` the docstring is where the
two-step contract is explained, because that is the only place the model reliably sees it.

## Errors Are Part of the Interface

This is the one thing that bites everybody on `mcp>=2`. The server forwards to the client
**only the message of a `ToolError`**. Any other exception reaches the model as the bare
text `Error executing tool kill_port`, and the explanation you carefully wrote vanishes.

The demo shows both, side by side:

```
wrapped error  -> Error executing tool kill_port: unknown or already-used confirm_token; request a new plan
unwrapped error-> Error executing tool demo_unwrapped_error
```

So the `tool()` decorator catches the failures an agent can act on (`Refused`, bad input,
psutil errors) and re-raises them as `ToolError` with the message intact:

```python
except (Refused, ValueError, psutil.Error) as e:
    raise ToolError(str(e)) from e
```

Two deliberate choices:

- The list is **explicit**. A genuine bug (`KeyError` from a typo) stays hidden from the client
  and shows up in the server's stderr, which is what you want: the model cannot fix your bug.
- Nothing is swallowed. Every expected failure becomes a message that says what happened and
  what to do next ("request a new plan", "run elevated").

When you run the demo you will see a Python traceback printed to the terminal for
`demo_unwrapped_error`. That is the server logging the hidden bug to stderr, as intended.

## stdout Is Sacred

In `--serve` mode **never `print()`**. Stdout is the protocol channel, and a stray line corrupts
the JSON-RPC stream. Logs go to stderr. That is also why the demo client and the server are the
same file in two modes: one file, `--serve` for the pipe's far end.

## Shape of the Server

| Tool | Job |
|------|-----|
| `whats_on_port(port)` | discovery, read-only |
| `kill_port(port, confirm_token=None)` | step 1 plan, step 2 execute |
| `check_port_reachable(host, port, timeout)` | TCP connect, distinguishes refused from other failures |

Three tools, not thirty. Fewer, well-described tools are chosen more reliably. The full ports-mcp
adds `list_listening`, `find_free_port` and `process_tree`, and gives `kill_port` the extra
`protocol`, `force` and `grace_seconds` arguments.

The server holds one `PlanStore` in memory. Tokens do not survive a restart, which is a feature.
`--ttl` makes token lifetime a flag so Module 07 can test expiry in one second.

## Run It

```bash
python 05-mcp-wrapper/main.py
```

To use it from a real client, register `python /path/to/05-mcp-wrapper/main.py --serve` as a stdio
MCP server, e.g. `claude mcp add ports-mini -- python /path/to/main.py --serve`.

## What's Missing

The server works on Windows, as shown. Module 06 looks at what changes on macOS and Linux, and
what we cannot hide.

→ [Next: Module 06: Cross-Platform Quirks](../06-cross-platform-quirks/README.md)
