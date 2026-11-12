# Offline printer mock

## Status and provenance

Default profile **`finder-v1.5-idle`** uses real-printer control-acquisition, identity and idle-status replies from firmware `V1.5 20170419`. Formatting and values match the selected capture except for an anonymized machine name and serial. The original **`synthetic-v1`** remains available with `--profile synthetic-v1`.

The user has successfully connected FlashPrint and polled idle status with the new profile; see observations FINDER-IDLE-003 and FINDER-MOCK-004 in [PROTOCOL.md](PROTOCOL.md). Reviewed reference bytes live in `tests/fixtures/finder-v1.5-idle.json`. Upload, errors, listing, release and control-policy behavior remain experimental mock conventions, not validated printer behavior. No response delays or physical dynamics are replayed.

## Start

Requires Python 3.11+. Run from the repository root:

```sh
python3 -m finderlab mock --verbose
python3 -m finderlab mock --help
```

Default endpoint: `127.0.0.1:8899/TCP`. No UDP sockets or discovery announcements are created. Port `0` requests an available port, printed on startup. Ctrl+C closes sessions and finalizes the capture manifest. All virtual files are lost on process exit, but their bytes remain in persistent captures.

For manual testing from a separate FlashPrint machine, explicitly bind to the mock host's LAN address:

```sh
python3 -m finderlab mock --host 192.0.2.20 --port 8899 --verbose
```

`192.0.2.20` is a documentation placeholder: replace it with your machine's actual address. This exposes an unauthenticated mock on that interface; use a trusted network and suitable firewall rules. Bind options do not connect to a printer.

If your FlashPrint version supports manual IP connection, point it at the mock. Connection and idle polling have been observed in the user's setup; compatibility with other client versions/profiles is unknown. Watch verbose output for unsupported commands and keep the FlashPrint version/UI error in your notes. Unknown commands produce an error rather than a misleading generic `ok`. Automatic discovery is not supported yet.

## Commands implemented

All commands must be ASCII, prefixed with `~`, and terminated by **CRLF** (`\r\n`). Commands are case-sensitive. Success replies have a `CMD <code> Received.` line, optional body, and an `ok` line. Errors are one `Error: ...` line with **no** `ok`.

| Command | Default captured-idle profile (other behavior remains synthetic) |
| --- | --- |
| `~M115` | `Flashforge Finder`, firmware `V1.5 20170419`, anonymized name/serial, captured field spacing and no MAC line. |
| `~M650` | Captured `X: 34 Y: 0`; read-only. |
| `~M105` | Fixed captured idle temperature `T0:21 /0 B:0 /0`; no heating. |
| `~M114` | Captured `X:0 Y:0 Z:0 A:0 B:0`; no movement. |
| `~M119` | Fixed ready/idle state with no current print. |
| `~M27` | Idle print progress (`0/0`). |
| `~M601 S1` | Captured success body `Control Success.`; device-wide ownership/conflict policy is synthetic. |
| `~M602` | Release owned control and discard pending upload; releasing with no owner is harmless. Cannot release another session's control. |
| `~M28 <size> 0:/user/<name>` | Owner only: validate limits and begin receiving exactly `<size>` raw bytes. |
| `~M29` | Owner only: atomically commit a fully received pending upload. No upload pending is an error. |
| `~M20` | Mock listing: `Begin file list`, sorted `name size` lines, `End file list`. Not verified Finder syntax. |

Identity/offset/status queries and listing do not require control. Arguments to status/listing/release/finish commands are rejected. Unsupported commands, including movement, heating and print-start, are logged as warnings and rejected. Nothing is physically or virtually printed in this version.

`M119` describes a non-printing device; it does not simulate busy/temperature/movement dynamics. Files are reflected in `M20`, not in the current-print field.

## Connection troubleshooting: M650

A user-reported FlashPrint attempt sent `M601 S1`, `M115`, `M650`, then released control and disconnected after the old mock rejected `M650`. The mock now answers that query with fixed synthetic XY values instead of an unsupported-command error. See observation **FP-M650-001** in [PROTOCOL.md](PROTOCOL.md) for evidence and limitations.

Restart the mock after updating and retry with `--verbose`. This removes one known unsupported command; it does not guarantee that FlashPrint will accept the response or complete connection. Report the next command sequence, any UI error and your FlashPrint version if it still disconnects.

## Upload state machine

```text
M601 S1 → M28 <N> <path> → exactly N raw bytes → M29 → committed virtual file
```

- No escaping, per-block ACK, CRC or fixed delay is implemented. This matches the current uploader's hypothesis, not an established Finder 2 protocol.
- Raw payload may contain nulls, arbitrary non-ASCII bytes, `ok`, CRLF and `~M29`; none are interpreted as commands.
- Surplus bytes after the Nth payload byte are retained for command parsing, including when payload and `M29` arrive in one socket read.
- After all N bytes arrive, only `M29` or `M602` is accepted until the pending upload is finished/discarded.
- Before all N bytes arrive, **every byte is payload**. A premature `M29` or `M602` cannot cancel it. Disconnect to abort, or wait for the idle timeout.
- Disconnect, timeout and server shutdown discard pending uploads and release session control.
- A replacement does not overwrite the old file until `M29`. Limits count the existing file plus the pending replacement, so an otherwise full device cannot replace a file in place.
- There is no resume or automatic retry. There is no distinction between syntactically valid G-code and arbitrary binary file contents.

Names are a single ASCII component, 1–128 characters: start with a letter, digit or underscore, followed by letters, digits, underscores, dots or hyphens; `..` anywhere is rejected. Paths must use the exact `0:/user/` prefix. No virtual path is opened on the host filesystem. Empty files are rejected.

## Resource limits

Defaults, all configurable through CLI flags:

| Flag | Default |
| --- | --- |
| `--idle-timeout` | 30 seconds, applied per command read, payload read and reply drain |
| `--max-file-size` | 8,388,608 bytes |
| `--storage-limit` | 33,554,432 bytes of committed + pending file content |
| `--max-files` | 32 committed names |
| `--max-clients` | 8 active TCP sessions |
| `--max-command-size` | 4,096 bytes, including CRLF |

Excess connections are closed without a protocol reply. Overlong command lines receive an error and are closed; timeout closes silently. These are deliberate mock policies, not claims about firmware behavior.

The storage limit measures file content, not process RSS. Python object overhead, transport buffers and a temporary copy during commit consume additional bounded memory. There is one pending upload at a time because there is one control owner.

## Logs and inspection

Both requests and replies are now recorded automatically to a per-run directory under `captures/`, printed at startup. `traffic.log` provides timestamped, session-tagged escaped previews; `events.jsonl` provides structured events; per-session `.bin` files preserve exact bytes, including binary uploads and partial commands. New runs retain all previous connection history. See [CAPTURES.md](CAPTURES.md) for format, privacy, metadata flags and limits.

`--verbose` additionally shows commands/replies on the console. No full binary upload dump is printed there, but persistent captures contain the payload. Unknown commands and abnormal termination produce console warnings even without verbose mode. Logs can contain private names, model content and addresses.

Python embedding is opt-in: pass `capture=Capture(...)` to `MockPrinter` and close the recorder after closing the server. Without that argument, embedding stays memory-only, as used by the original unit tests. `MockPrinter.files` remains a read-only mapping of committed names to bytes. Replay and standalone capture inspection/validation tools are not implemented yet.

## Testing

```sh
python3 -m unittest discover -s tests -v
```

The suite uses `unittest.IsolatedAsyncioTestCase`, standard-library clients and ephemeral loopback endpoints. It covers parsing/fragmentation, pipelined commands, binary uploads, commit/discard, replacement, control conflicts, limits, timeout, shutdown and the unchanged uploader. No physical printer or FlashPrint instance is used.

Independent fixture tests compare the captured connection/polling prefix byte-for-byte, including coalesced commands and reordered polling. Existing synthetic-profile tests remain explicit. Next evidence needed: upload framing and job control, error handling and discovery; the idle baseline alone does not establish those behaviors.
