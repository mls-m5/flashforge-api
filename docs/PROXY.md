# Recording TCP proxy

## Purpose and limitations

The proxy relays FlashPrint to an explicit target IP/port and records both byte streams. It does not parse commands, normalize line endings, inject handshakes, add protocol delays or modify replies. This lets us compare actual printer responses with the synthetic mock rather than guessing what FlashPrint expects.

**It is not a safety filter.** All commands, including heating, movement, deletion and print-start, pass through. Hardware testing requires explicit approval and physical supervision. Closing a network connection is not an emergency stop.

The implementation has been tested only with localhost fake servers. Finder 2/FlashPrint compatibility, real-world timing and discovery behavior are unverified. No physical printer was contacted during development.

## Start against a real printer (manual, supervised use only)

First stop the mock if it occupies local port 8899. Replace `192.0.2.10` below with your actual printer IP; it is a documentation placeholder:

```sh
python3 -m finderlab proxy --target-host 192.0.2.10 --target-port 8899
```

By default the proxy listens on `127.0.0.1:8899`. On that same computer, manually connect FlashPrint to **127.0.0.1**, not the real printer IP. Start with connection/status only, then disconnect; do not select print or upload-and-print merely to collect an identity response.

The target is contacted only when a client connects to the proxy. Startup does not scan the network or probe the printer. Targets must be literal IPv4/IPv6 addresses; DNS hostnames are deliberately unsupported. Obvious self-targets are rejected to avoid relay loops.

If FlashPrint runs on another computer, explicitly bind the proxy to the proxy host's trusted LAN address with `--host`, and point FlashPrint at that address. Do not expose it to the internet or an untrusted network. There is no authentication.

Automatic discovery is not proxied. FlashPrint might rediscover the real printer and bypass our endpoint: verify that a session actually appears in the printed capture directory. A UI connection indicator alone is not proof of interception. If manual addressing is unavailable, obtain a host packet capture before implementing discovery replies.

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
- Shutdown cancels sessions and closes both endpoints. Recording errors stop forwarding and cause CLI failure, not silent log loss.

The proxy preserves byte order/content per direction, not packet boundaries or precise timing. If a connection differs from a direct FlashPrint connection, compare bytes and host packet captures before changing protocol behavior.

## Diagnosing the current FlashPrint disconnect

The latest reported mock sequence is `M601 S1 → M115 → M650 → M115 → M602 → disconnect`. No command in this sequence is now unsupported. The second identity query does **not** prove FlashPrint accepted the synthetic identity; it may be rechecking a response and then releasing control.

Possible causes include identity/model recognition, synthetic firmware/version formatting, required response fields, or an offset-response mismatch. These are hypotheses, not a diagnosis. The useful next experiment is a successful real-printer connection through this proxy using the same FlashPrint version/profile, then a field-by-field and byte-for-byte comparison with a recorded mock attempt.
