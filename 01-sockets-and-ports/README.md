# Module 01: Sockets and Ports

## The Concept

"What is using port 3000?" sounds like a question about a port. It is really a question
about the operating system's table of sockets. Before reaching for any library, build the
mental model with nothing but the standard library.

A **port** is a 16-bit number the OS uses to hand an incoming connection to the right
program. A program claims one with two calls:

```python
s = socket.socket()
s.bind(("127.0.0.1", 3000))   # "this address and port are mine"
s.listen()                    # "and I am now accepting connections"
```

`bind` claims the (address, port) pair. `listen` turns the socket into a *listener* and the
OS starts completing TCP handshakes for it, even before your code calls `accept()`. A
socket that is bound but not listening is not something a client can connect to, and
(on most systems) not something a tool like this one will list.

## Three Facts the Whole Server Depends On

**1. Port 0 means "pick one for me".** `bind(("127.0.0.1", 0))` lets the OS choose a free
port and `getsockname()[1]` tells you which. Every test in this course uses it. A hard-coded
port like 8080 works on your machine and fails on CI the day something else is using it.

**2. One listener per address and port.** A second `bind` to a busy port fails with
`EADDRINUSE` (Windows says `WSAEADDRINUSE`, error 10048). That error is the thing developers
actually hit ("Address already in use") and the reason this server exists.

**3. The bind address decides who can reach you.**

| Bound to | Reachable from | The server calls it |
|----------|----------------|---------------------|
| `127.0.0.1`, `::1` | this machine only | loopback only |
| `0.0.0.0`, `::` | every network interface, so the LAN, Wi-Fi, a coffee-shop network | **EXPOSED** |
| `192.168.1.20` | only through that one interface | one interface |

This is a security signal, not trivia. A dev server started with `--host 0.0.0.0` is
reachable by everyone on the network. The demo proves it by connecting to your own LAN
address: the `0.0.0.0` listener answers, the `127.0.0.1` one does not.

`exposure()` in `main.py` classifies an address with the `ipaddress` module instead of
string matching. That handles IPv6, IPv4-style loopbacks such as `127.0.0.2`, and zone ids
like `fe80::1%eth0`.

## Two Ways a Connection Fails

- **Refused** (`ConnectionRefusedError`): the machine answered "nothing is listening here".
  The host is up.
- **Timed out**: nothing answered at all. A firewall dropped the packet, or the host is down.

An agent needs to tell these apart, and Module 05's `check_port_reachable` does. One trap
the demo avoids: on Windows a refused connection to *localhost* is retried for about two
seconds before the error arrives, so a 2-second timeout makes a closed local port look
like a firewall drop. The demo uses 5 seconds.

## Run It

```bash
python 01-sockets-and-ports/main.py
```

It asserts each fact above on your machine. Step 6 needs a network interface and says so
if it is skipped.

## What's Missing

We can create listeners but cannot find *other people's*. Module 02 asks the OS who is
listening, and who owns each socket.

→ [Next: Module 02: psutil](../02-psutil/README.md)
