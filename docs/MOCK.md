# Synthetic printer mock

## Status and provenance

Profile **`synthetic-v1`** is a local testing convention, not a captured Finder 2 firmware profile. Command names are drawn from the hypotheses and external reports already listed in [PROTOCOL.md](PROTOCOL.md). Identity fields, status values, errors, listing syntax, control policy and transfer semantics have **not** been verified against Finder 2 or FlashPrint.

The mock is useful for testing the existing uploader, stream handling, session ownership and upload failure paths. A successful test against it is not independent evidence that the uploader implements the physical printer's protocol correctly.

## Start

Requires Python 3.11+. Run from the repository root:

```sh
python3 -m finderlab mock --verbose
python3 -m finderlab mock --help
```

Default endpoint: `127.0.0.1:8899/TCP`. No UDP sockets or discovery announcements are created. Port `0` requests an available port, printed on startup. Ctrl+C closes sessions; all virtual files are lost on process exit.

For manual testing from a separate FlashPrint machine, explicitly bind to the mock host's LAN address:

```sh
python3 -m finderlab mock --host 192.0.2.20 --port 8899 --verbose
```

`192.0.2.20` is a documentation placeholder: replace it with your machine's actual address. This exposes an unauthenticated mock on that interface; use a trusted network and suitable firewall rules. Bind options do not connect to a printer.

If your FlashPrint version supports manual IP connection, point it at the mock. Whether it accepts this synthetic identity and proceeds is unknown. Watch verbose output for unsupported commands and keep the FlashPrint version/UI error in your notes. Unknown commands produce an error rather than a misleading generic `ok`. Automatic discovery is not supported yet.

## Commands implemented

All commands must be ASCII, prefixed with `~`, and terminated by **CRLF** (`\r\n`). Commands are case-sensitive. Success replies have a `CMD <code> Received.` line, optional body, and an `ok` line. Errors are one `Error: ...` line with **no** `ok`.

| Command | Synthetic behavior |
| --- | --- |
| `~M115` | Finder 2 label, explicitly synthetic firmware, mock name/serial/MAC. |
| `~M105` | Fixed idle temperature values; no heating. |
| `~M114` | Fixed zero coordinates; no movement. |
| `~M119` | Fixed ready/idle state with no current print. |
| `~M27` | Idle print progress (`0/0`). |
| `~M601 S1` | Acquire device-wide control; repeat claim by the owner succeeds. Another owner's claim fails. |
| `~M602` | Release owned control and discard pending upload; releasing with no owner is harmless. Cannot release another session's control. |
| `~M28 <size> 0:/user/<name>` | Owner only: validate limits and begin receiving exactly `<size>` raw bytes. |
| `~M29` | Owner only: atomically commit a fully received pending upload. No upload pending is an error. |
| `~M20` | Mock listing: `Begin file list`, sorted `name size` lines, `End file list`. Not verified Finder syntax. |

Status queries and listing do not require control. Arguments to status/listing/release/finish commands are rejected. Unsupported commands, including movement, heating and print-start, are logged as warnings and rejected. Nothing is physically or virtually printed in this version.

`M119` describes a non-printing device; it does not simulate busy/temperature/movement dynamics. Files are reflected in `M20`, not in the current-print field.

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

`--verbose` enables connection and command logging. Commands are escaped before display; binary upload data is not printed. Unknown commands and abnormal upload termination produce warnings even without verbose mode. Filenames and peer addresses in logs may be private.

This is **not** the recording format proposed in [CAPTURES.md](CAPTURES.md). There are no raw byte capture files, timestamps/offset manifests, disk exports or replay yet. For raw traffic, use a separately approved host-local packet capture. In Python tests/embedding, `MockPrinter.files` provides a read-only mapping of committed filenames to bytes.

## Testing

```sh
python3 -m unittest discover -s tests -v
```

The suite uses `unittest.IsolatedAsyncioTestCase`, standard-library clients and ephemeral loopback endpoints. It covers parsing/fragmentation, pipelined commands, binary uploads, commit/discard, replacement, control conflicts, limits, timeout, shutdown and the unchanged uploader. No physical printer or FlashPrint instance is used.

Next evidence needed: real Finder 2 connection/status and successful upload captures, plus discovery queries/replies. Use these to add a distinct capture-derived profile rather than silently presenting this one as hardware-accurate.
