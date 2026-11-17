# Recording TCP proxy

## Purpose and limitations

The proxy relays FlashPrint to an explicit target IP/port and records both byte streams. It does not parse commands, normalize line endings, inject handshakes, add protocol delays or modify replies. This lets us compare actual printer responses with the synthetic mock rather than guessing what FlashPrint expects.

**It is not a safety filter.** All commands, including heating, movement, deletion and print-start, pass through. Hardware testing requires explicit approval and physical supervision. Closing a network connection is not an emergency stop.

Automated tests use only localhost fake servers; the coding agent has not contacted hardware. User-collected proxy runs now establish connection/status and one file-transfer/start/cancel workflow on the user's Finder. Those bounded observations do not establish all firmware variants, error handling, timing requirements or discovery behavior.

## Start against a real printer (manual, supervised use only)

First stop the mock if it occupies local port 8899. Replace `192.0.2.10` below with your actual printer IP; it is a documentation placeholder:

```sh
python3 -m finderlab proxy --target-host 192.0.2.10 --target-port 8899
```

By default the proxy listens on `127.0.0.1:8899`. On that same computer, manually connect FlashPrint to **127.0.0.1**, not the real printer IP. Start with connection/status only, then disconnect; do not select print or upload-and-print merely to collect an identity response.

The target is contacted only when a client connects to the proxy. Startup does not scan the network or probe the printer. Targets must be literal IPv4/IPv6 addresses; DNS hostnames are deliberately unsupported. Obvious self-targets are rejected to avoid relay loops.

If FlashPrint runs on another computer, explicitly bind the proxy to the proxy host's trusted LAN address with `--host`, and point FlashPrint at that address. Do not expose it to the internet or an untrusted network. There is no authentication.

Automatic discovery is not proxied. FlashPrint might rediscover the real printer and bypass our endpoint: verify that a session actually appears in the printed capture directory. A UI connection indicator alone is not proof of interception. If manual addressing is unavailable, obtain a host packet capture before implementing discovery replies.

## Short web workflow scripts

`./tools/start_printer_proxy.sh CONFIRMED_IP` wraps the proxy with loopback
listener port9000 and default upstream8899. The IP argument is required; a
remembered address is not independently verified. `--port`/`--target-port`
overrides are forwarded explicitly. `./tools/start_proxy_web.sh` starts the
separate page targeting that proxy. It enables Save only; generated-output
saving and job controls require separate flags. See [WEB.md](WEB.md) for exact
commands, local dummy rehearsal and physical candidate blockers. Starting the
proxy/page does not itself contact hardware. Ordinary browser actions can.

## Local-only trial without hardware

Terminal 1:

```sh
python3 -m finderlab mock --port 9000
```

Terminal 2:

```sh
python3 -m finderlab proxy --target-host 127.0.0.1 --target-port 9000
```

A client connecting to local port 8899 now reaches the mock through the proxy. This exercises transport/recording only, not physical-printer compatibility.

## Passive web status while FlashPrint is polling

`./tools/watch_printer.sh` serves a separate read-only page on localhost8001,
deriving status from existing recordings for the loopback proxy on port9000.
It does not connect to the printer, claim control or inject polling commands.
The ordinary proxy web launcher includes the same panel on its next restart.
Source/session/upstream and individual observation ages are visible; stale
captures are not labelled live. See [STATUS.md](STATUS.md). Without existing
polling traffic there are no new observations; a transparent proxy does not
make the printer push status spontaneously.

## Logs and historical sessions

Each invocation creates a new run directory under `captures/`. It contains `traffic.log`, `events.jsonl`, a manifest and exact binary streams for each session. See [CAPTURES.md](CAPTURES.md) for reading, limits and privacy. `--verbose` does not change capture fidelity; recordings are written regardless of console verbosity.

Optional context:

```sh
python3 -m finderlab proxy --target-host 192.0.2.10 \
  --flashprint-version YOUR_VERSION --experiment-id connection-baseline
```

Stop with Ctrl+C before asking for final hashes/summaries. Keep the run directory intact. Provide its path rather than pasting terminal output when the assistant can access the same workspace.

## Transport behavior

- Separate upstream connection per incoming session, maximum eight active clients by default.
- Continuous bidirectional reads/writes, fixed 64 KiB read chunks and transport backpressure.
- EOF is forwarded as a half-close; the opposite direction remains open for a final reply.
- `--connect-timeout` defaults to 8 seconds.
- `--idle-timeout` defaults to 60 seconds of inactivity **across both directions**. A one-way but active upload does not expire merely because the printer is silent. Individual blocked writes also have this timeout.
- Refusal, timeout and connection errors are recorded; the proxy closes the client without injecting a fake printer reply.
- Shutdown stops accepting, cancels/joins sessions and closes both endpoints **before** awaiting listener closure. Python3.12+ `Server.wait_closed()` also waits for accepted connections; waiting first incorrectly left shutdown to the60-second idle watchdog. Portable drain-order regressions enforce this without sleeps/timeouts being lengthened. Recording errors stop forwarding and cause CLI failure, not silent log loss.

Python API reference: [Server.wait_closed (Python3.12)](https://docs.python.org/3.12/library/asyncio-eventloop.html#asyncio.Server.wait_closed).
The reported host failure was on Python3.12; agent validation uses Python3.11
plus explicit active-handler ordering assertions, not a claimed native3.12 run.
No protocol framing/CRC/status parser/retry change or hardware test follows.

The proxy preserves byte order/content per direction, not packet boundaries or precise timing. If a connection differs from a direct FlashPrint connection, compare bytes and host packet captures before changing protocol behavior.

## What the proxy comparison established

The old synthetic identity led to `M601 S1 → M115 → M650 → M115 → M602 → disconnect`. Real-printer replies differed in control-success text, machine type/firmware fields, whitespace, offsets and status formatting. After adopting the reviewed idle bytes (name/serial anonymized), the user's mock recording showed sustained polling without protocol errors. The repeated identity query also occurs in a successful real-printer session; it is not itself a failure indicator. No single field was isolated as the cause.

A later user run captured framed file transfer and distinct `M23` start / `M26` cancel. See FINDER-IDLE-003 through FINDER-UPLOAD-005 in [PROTOCOL.md](PROTOCOL.md) for provenance and limits. Upload is not raw file bytes on this firmware. Do not blindly replay the whole run: the cancel is optional, and a print-start may heat/move the real printer. The updated default dummy handles these as separate virtual operations.
