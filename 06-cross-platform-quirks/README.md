# Module 06: Cross-Platform Quirks

## The Concept

psutil hides most differences between Windows, macOS and Linux. It does not hide all of them,
and the ones it leaves are exactly where a port tool goes wrong. `main.py` probes each quirk on
the machine you run it on and asserts the behavior it expects for that OS, so it doubles as a
regression test for the assumptions the server makes.

**Honesty note:** the author developed this on Windows 11. The Linux and macOS expectations below
come from documentation and psutil's behavior, and the module's assertions encode them, but
they were not run on those systems during development. CI for the full project runs the tests
on all three, which is where they get checked for real.

## The Quirks

### 1. What you can see depends on privilege and OS

| OS | Unprivileged `net_connections()` |
|----|----------------------------------|
| Windows | works; owners visible; some processes refuse name/cmdline/cwd |
| Linux | works; sockets of other users listed with `pid=None` |
| macOS | raises `AccessDenied` for the whole call; needs root |

The macOS case is handled by asking each process separately (`proc.net_connections()`), skipping
those that refuse, and **telling the user how many were skipped** so they know the list may be
incomplete. The `pid=None` case is shown as "unidentified process (elevation needed)". A
`whats_on_port` for a port that looks empty also tries a real connect: a successful connection
to a "free" port means something is hiding.

### 2. A listener's status may not be `LISTEN` (Windows)

See Module 02. The test prints the status psutil reports for a plain listening socket here
(`NONE` on the author's machine).

### 3. `SO_REUSEADDR` means different things

On POSIX it only allows rebinding a port in `TIME_WAIT`; a live listener still blocks you. On
Windows it lets a second socket bind a port that is **actively in use**. If `find_free_port` set it
while probing, Windows would call every busy port free. The probe sets nothing, and step 3
proves the difference on your OS.

### 4. `terminate()` is polite on POSIX and brutal on Windows

POSIX `terminate()` sends SIGTERM, which a process may handle or ignore. Windows has no
equivalent for arbitrary programs; `terminate()` is `TerminateProcess`, an immediate hard
kill. So "graceful, then force after N seconds" is real on Linux and macOS and collapses to
"immediate" on Windows. The plan text says so, and the tests assert escalation only on POSIX.

### 5. Reserved port ranges (Windows)

Hyper-V, WSL and Docker reserve port ranges (`netsh int ipv4 show excludedportrange
protocol=tcp`). Nothing is listening there, yet `bind()` fails with WinError 10013. A free-port
finder that only checks "is anything listening?" will hand out a port nobody can use.
`find_free_port` does both checks: not listening *and* bindable.

### 6. Dual-stack sockets

A socket on `::` with `IPV6_V6ONLY` off serves IPv4 and IPv6. Windows reports it as two rows
(`0.0.0.0` and `::`); Linux reports one. Counting rows would give different numbers per OS,
so the server groups per process and port and prints each address.

### 7. Slow refusal on Windows loopback

Covered in Module 01: a closed local port takes about two seconds to say "refused". The full
server's timeout message mentions this.

## Not Probed Here

- **macOS system services** such as ControlCenter (the AirPlay Receiver) hold ports 5000 and 7000
  and are the usual answer to "what is on port 5000?". The server treats them as OS services
  (needing `force`) and says to disable the feature in System Settings instead.
- **Windows PID 4** (`System`) holds ports via `http.sys` for IIS and similar. It is on the hard
  refusal list, with advice to stop the service instead.

## Run It

```bash
python 06-cross-platform-quirks/main.py
```

## What's Missing

Every module so far ran its own demo. Module 07 shows how to test the finished server end to
end without mocking a single process.

→ [Next: Module 07: Testing It For Real](../07-testing-it-for-real/README.md)
