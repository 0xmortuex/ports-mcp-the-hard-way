# Module 02: psutil

## The Concept

`netstat -ano` on Windows, `lsof -i` on macOS and `ss -ltnp` on Linux all answer "who is
listening". Their output formats differ, they need different parsing, and some are not
installed by default. [psutil](https://github.com/giampaolo/psutil) asks the OS through its
native APIs and gives the same Python objects everywhere. That is why this server needs
no per-platform code for discovery.

## Two Calls

```python
for c in psutil.net_connections(kind="inet"):     # every TCP/UDP socket
    c.laddr.ip, c.laddr.port, c.status, c.pid      # local address, state, owner

p = psutil.Process(pid)
p.name(), p.cmdline(), p.cwd(), p.username()       # what the owner is
```

"Listening" is `c.status == psutil.CONN_LISTEN` for TCP. A UDP socket has no handshake, so
a bound UDP socket with no remote address is the equivalent (the full server handles UDP;
this module sticks to TCP).

## Filtering Is the Whole Query

`listeners()` returns every listener sorted by port, and "what is on port 3000" is a filter
over it. `describe(pid)` turns the PID into something a human (or a model) can use: the
command line says `vite` or `uvicorn app:app --reload`, the working directory says which
project. That is how the full server can say "this is your Vite dev server in
`C:\work\shop`" instead of "node.exe PID 4412".

## Failure Is Information

Run the demo and step 4 prints something like `97 process(es) hide details from this
user`. That is normal. System services, other users' processes and antivirus engines refuse
to answer. `psutil` raises `AccessDenied`, and what you do with it matters:

```python
try:
    setattr(info, attr, getattr(p, attr)())
except psutil.AccessDenied:
    info.denied.append(attr)     # remember WHAT was refused
```

Two bad options: let it crash the tool, or catch it and show an empty command line. The
empty line is worse, because it says "this process has no command line", which is false. The
server records the refused fields and prints `<unavailable: access denied, elevation
needed>`. The user learns the fix (run elevated) instead of a wrong fact.

The same applies to the socket table. On Linux without root, other users' sockets are listed
but `c.pid` is `None`. On macOS without root, `net_connections()` raises `AccessDenied` for
the whole call. Module 06 covers both.

## A Windows Surprise: Status NONE

On this author's Windows 11 build (10.0.26300), a plain `socket.listen()` shows up in psutil
with status `NONE`, not `LISTEN`, and `netstat` does not list it at all (raw
`GetExtendedTcpTable` returns state 0). The socket accepts connections fine. A server that
only trusts `LISTEN` would report "nothing on port N" for a port that is clearly in use.
`is_listener()` therefore also accepts, on Windows only, a TCP socket with state `NONE` and no
remote address. This was found by the tests failing, not by reading documentation. It may
only affect some builds or restricted-process contexts; the rule is safe either way because
a *connected* socket always has a remote address.

## The PID You Find Is Not Always the PID You Started

Step 3 shows that on Windows, a virtualenv's `python.exe` is a small launcher that starts the
real interpreter as a child. `Popen.pid` is the launcher; the listener is its child. Any code
that compares "the PID I spawned" with "the PID listening" must allow for descendants. Both
the tests and the server do.

## Run It

```bash
python 02-psutil/main.py
```

It starts a real `python -m http.server` on an OS-assigned port, finds it, describes it, and
checks the port is free after killing it.

## What's Missing

A dev server is rarely one process: `npm run dev` starts node, which starts esbuild. Killing
only the process holding the port can leave pieces behind or get undone. Module 03 is about
the tree.

→ [Next: Module 03: Process Trees](../03-process-trees/README.md)
