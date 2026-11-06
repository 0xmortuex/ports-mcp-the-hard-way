# Ports MCP: The Hard Way

Build an MCP server that answers "what is using port 3000?" and frees it **safely**, from raw
sockets up. No wrappers hiding how it works, every line explained, every module run for real.

At the end you will have built a small version of [ports-mcp](https://github.com/0xmortuex/ports-mcp)
yourself, and you will understand the parts most MCP tutorials skip: how to **let a model
trigger something destructive without letting it hurt you**, and how to test a process-killing tool
against real processes instead of mocks.

## Why This Exists

Most MCP tutorials stop at a weather API. The hard part of a useful server is elsewhere:

- asking the operating system the right question, and being honest when it refuses to answer
- not trusting what you just read (a PID can be reused; a process can respawn)
- designing a destructive tool so a confused model costs one extra message, not a lost database
- behaving the same on Windows, macOS and Linux, or saying clearly where it cannot
- tests that start real listeners on random ports and check the real port afterwards

## Who This Is For

- Developers who built a "hello world" MCP server and want to build a real one
- Anyone who has typed `netstat -ano | findstr :3000` or `lsof -i :3000` one time too many
- Anyone designing tools that give an AI agent power over a machine

**Prerequisites:** Python 3.10+ and basic familiarity with sockets. Then
`pip install -r requirements.txt`. No QEMU, no admin rights, no containers. Node is not needed.

## Modules

| # | Module | What You'll Build |
|---|--------|-------------------|
| 01 | [Sockets and Ports](01-sockets-and-ports/) | What bind/listen really do, why `0.0.0.0` is a security fact, refused vs timed out |
| 02 | [psutil](02-psutil/) | Port to PID to command line to working directory, and treating AccessDenied as information |
| 03 | [Process Trees](03-process-trees/) | Descendants, ancestors, PID reuse, and a supervisor that undoes your kill |
| 04 | [Safety and Confirm Tokens](04-safety-and-confirm-tokens/) | Plan then confirm, single-use expiring port-bound tokens, hard refusals, terminate then kill, verify |
| 05 | [The MCP Wrapper](05-mcp-wrapper/) | A stdio MCP server, agent-readable errors (`ToolError`), tested over the real transport |
| 06 | [Cross-Platform Quirks](06-cross-platform-quirks/) | Visibility by privilege, `SO_REUSEADDR`, SIGTERM vs Windows, reserved ranges, dual-stack |
| 07 | [Testing It For Real](07-testing-it-for-real/) | Real listener fixtures, ground-truth assertions, injectable time, and what one machine cannot prove |

Each module contains:
- **`README.md`**: the concepts and design decisions
- **`main.py`**: a working, commented implementation that asserts its own claims
- **`break-it.md`**: challenges that break your own code, with hints

Each `main.py` stands alone: no imports between modules. Module 05 repeats Module 04's kill
core verbatim, and `verify.py` checks the two copies never drift.

## Run It

```bash
pip install -r requirements.txt
python 04-safety-and-confirm-tokens/main.py     # any single module
python verify.py                                 # every module, plus the drift check
```

`verify.py` exits non-zero if any module's assertions fail.

## Verified Where?

Everything here was run on Windows 11 (Python 3.12). The Linux and macOS behavior described in
Module 06 comes from documentation and is encoded as assertions, but has not been run on those
systems by the author. Run `python verify.py` on your platform; where it disagrees with the text,
the code is right and the text needs a fix.

## Architecture

```
 AI agent (Claude Desktop, Claude Code, ...)
        |  MCP over stdio: JSON-RPC tool calls               <- Module 05
        v
 +----------------------------------------------------+
 | tools: whats_on_port, kill_port(plan|confirm), ...  |   <- Module 05
 |   +-- safety: plan, tokens, refusals, verify          |   <- Module 04
 |   +-- trees:  children, parents, identity             |   <- Module 03
 |   +-- psutil: sockets -> pids -> process details      |   <- Module 02
 +----------------------------------------------------+
        |  the operating system's socket table            <- Module 01, 06
```

## License

MIT
