# Break It: Sockets and Ports

## Challenge 1: Bind Without Listen

Remove `a.listen()` in step 1. Which later step fails first, and why? Then check whether the
bound-but-not-listening socket appears in `psutil.net_connections(kind="tcp")` on your OS.

**Hint:** Connections are refused until `listen()` runs. Whether the table shows a
bound-only TCP socket differs by operating system, which is why the server looks at the
socket state rather than at "has a local port".

## Challenge 2: The Short Timeout

Change `timeout=5` in `can_connect` to `timeout=0.5` and run the demo on Windows. What does
step 4 report now?

**Hint:** Windows keeps retrying a refused loopback connection, so you get `TimeoutError`
instead of `ConnectionRefusedError`. Linux and macOS refuse instantly. A tool that reports
"firewall" for a closed local port is lying to the agent.

## Challenge 3: A Hard-Coded Port

Replace port 0 with `8080` and run the module twice at the same time. Then run it once while
a dev server is on 8080. What do you learn about tests that pick ports by hand?

## Challenge 4: Classify Weird Addresses

Add `127.0.0.2`, `::ffff:127.0.0.1` and `169.254.1.1` to the table in step 5. Predict each
answer before running. `::ffff:127.0.0.1` is an IPv4 address wearing an IPv6 costume; does
`exposure()` see through it? (The full server's version unwraps it.)
