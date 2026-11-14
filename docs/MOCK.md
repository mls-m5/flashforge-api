# Offline printer mock

## Profiles and evidence

The default **`finder-v1.5`** combines observed connection/idle replies and framed upload/job-command responses from the user's Finder (reported as Finder 2), firmware `V1.5 20170419`. Private identity is replaced with name `Mock Find` and synthetic serial `F1AB0001`.

```sh
python3 -m finderlab mock --verbose
```

Requires Python 3.11+, no installation/dependencies. Default endpoint: `127.0.0.1:8899/TCP`. Stop the proxy first if it uses that port. Manually connect FlashPrint to this address. No UDP discovery is implemented. Use `--host YOUR_LAN_ADDRESS` only for deliberate exposure on a trusted LAN.

Other profiles:

```sh
python3 -m finderlab mock --profile finder-v1.5-idle
python3 -m finderlab mock --profile synthetic-v1
```

- `finder-v1.5`: captured-style idle replies, block upload and explicit virtual start/cancel.
- `finder-v1.5-idle`: earlier captured idle replies, with the original experimental **raw** upload and no job controls.
- `synthetic-v1`: original invented identity/status and raw-upload conventions.

The user's finalized FlashPrint-to-mock run now includes connection, a 3668165-byte upload, virtual start and explicit cancel (FINDER-MOCK-007). The new upload CLI has also sent the provided GX to a fresh dummy with exact byte equality and no job started (CLIENT-UPLOAD-008). This is not firmware emulation or a physical model. See [PROTOCOL.md](PROTOCOL.md), FINDER-IDLE-003 through FINDER-UPLOAD-005.

## Commands

Commands are ASCII, prefixed with `~` and terminated by CRLF. Success replies use `CMD <code> Received.`, optional body, then `ok`, all CRLF-terminated. Block ACKs are different: `N<index> ok\r\n`. Errors are mock-policy `Error: ...` lines without `ok`.

| Command | Default `finder-v1.5` behavior |
| --- | --- |
| `M601 S1` | Captured `Control Success.` body; acquire control. |
| `M115` | Captured field order/spacing, `Flashforge Finder`, real firmware text, anonymized name/serial, no MAC line. |
| `M650` | Captured `X: 34 Y: 0`. |
| `M114` | Captured `X:0 Y:0 Z:0 A:0 B:0`; no movement. |
| `M105` | Idle `T0:21 /0 B:0 /0`; virtual active job `T0:21 /220 B:0 /0`. |
| `M119` | Captured idle status, or representative virtual `BUILDING_FROM_SD` / `WAIT_ON_TOOL` status. |
| `M27` | Idle `0/0`; virtual active job `0/<logical file size>`. No simulated progress. |
| `M28 <size> 0:/user/<name>` | Owner only: validate limits, reply `Writing to file: ...  Length: ...`, receive block frames. |
| `M29` | Owner only: commit a fully received file and reply `Done saving file.` **Does not start printing.** |
| `M23 0:/user/<name>` | Owner only: select an existing file and start a virtual job; captured `File opened: ... Size: ...` / `File selected` reply. |
| `M26` | Owner only: explicitly cancel the virtual job. Does not delete its file. |
| `M602` | Release control/discard pending upload. Does **not** cancel an active virtual job. Release success reply is now hardware-observed (CLIENT-UPLOAD-009); discard/ownership policies remain synthetic. |
| `M20` | Mock-only sorted `name size` listing; not an evidenced Finder listing format. |

Read-only queries/listing do not require control in the mock. A second session cannot steal/release another's control. Ownership/error policies, unsupported arguments, idempotent cancel and busy rejection are not firmware-verified.

Unknown commands (including generic motion/heating commands) are logged and rejected, not silently acknowledged. The mock has **no outgoing printer connection and never executes G-code**. Temperature targets and endstops are virtual response values only.

## Web-only manual rehearsal is separate from this wire protocol

The owned-dummy web page now has a counter/light rehearsal panel
([MANUAL_CONTROLS.md](MANUAL_CONTROLS.md)). It does not send or acknowledge
motion/heating/LED G-code, change M114/M105 replies or execute stored files.
Its synthetic warm flag and relative counters are explicitly not printer
feedback or a validated firmware model. Configured loopback endpoints do not
gain this capability; only a new dummy owned by the web process does.

## Captured block-upload mode

```text
M601 S1 → M28 <N> <path> → framed blocks + per-block ACKs → M29 → saved file
                                                                │
                                      optional M23 → virtual job → optional M26
```

A frame is always **4112 wire bytes**:

- 4 magic bytes `5a 5a a5 a5`;
- 4-byte unsigned big-endian block index, starting at zero;
- 4-byte unsigned big-endian logical data length;
- 4-byte unsigned big-endian CRC32 (`zlib.crc32`) over logical data only;
- 4096 bytes containing logical data followed by zero padding.

Non-final logical blocks are 4096 bytes. The last carries the remaining count and is zero-padded on the wire. Headers/padding do not count toward the declared file size. After validation the mock sends `N0 ok`, `N1 ok`, etc. It retains surplus bytes when a frame, padding and next command share one read. Payload strings such as `~M29`, `~M26` and `ok` are never executed as commands.

Observed reference transfers: 102989 logical bytes / 26 frames (last logical length 589), and 3668165 bytes / 896 frames (last logical length 2245). All 922 source headers, CRCs, padding and ACKs were checked offline. The second transfer also demonstrates unquoted filenames containing spaces. Other firmware variants and retry behavior are not established.

Invalid magic, index, length, CRC or padding gives a mock error and closes the session. No retransmission/resume behavior is invented. Disconnect/timeout before `M29` discards the temporary file; a previous committed version remains intact. After all data arrives, finish with `M29` or discard with `M602`. During a partial frame, command bytes are still data; disconnect to abort.

**The original `upload.py` does not implement this framing/ACK format.** The new `python3 -m finderlab upload FILE` does; see [CLIENT.md](CLIENT.md). FlashPrint is another supported trial client. For testing the old uploader locally, explicitly select `synthetic-v1`; passing against that profile is not hardware validation.

## Virtual jobs: never automatically cancel

Saving, starting and cancelling are independent operations. Upload-only stays idle. A virtual job starts only after `M23`, persists through control release/disconnect/repeated polling, and is cancelled only by `M26` (or disappears with process exit). There is no recorded-script cursor that automatically reaches the captured abort, and no timed completion.

The active-job status is a fixed representative snapshot. It does not reproduce homing phases, thermal dynamics, cancellation transients or GX execution offsets. In the real capture, progress denominator differed from GX size; the mock deliberately reports zero over file size instead of pretending to understand that execution layout. Cancelling returns immediately to virtual idle, unlike the real printer's transient states.

Uploads/new starts while a virtual job is active are rejected rather than replacing/cancelling it implicitly. Stored bytes are never parsed or executed.

## Limits and storage

Default limits (CLI-configurable): 8 MiB per file, 32 MiB committed + pending logical content, 32 committed names, eight active clients, 4096-byte command lines including CRLF, 30-second inactivity/read/write timeout. Names are one ASCII component, 1–128 characters: letter/digit/underscore first, then letters/digits/underscores/dots/hyphens. The framed `finder-v1.5` profile also accepts internal ASCII spaces, preserving them exactly; `M28` splits only the size from the path and `M23` treats the entire remainder as its path. Legacy raw profiles still reject spaces. Leading/trailing spaces, tabs, control characters, path separators and `..` are rejected as mock safety policy. Exact path prefix: `0:/user/`. No remote path is opened on the host filesystem.

Storage quota counts the old version while receiving its replacement. Python/transport overhead and the temporary commit copy consume additional bounded memory. Empty files are rejected. Excess clients are closed; timeout closes silently; overlong lines receive an error and close. These limits/error policies are mock conventions.

Files and jobs are memory-only and disappear with the process. **Capture files persist uploaded bytes on disk.** Each CLI run prints its private capture directory under `captures/`, containing `traffic.log`, `events.jsonl`, manifest and per-session binary streams. Ctrl+C finalizes it. See [CAPTURES.md](CAPTURES.md) for privacy/quotas. `--verbose` also prints requests/replies on the console.

Embedding is opt-in for recording: pass a `Capture` to `MockPrinter` and close it after the server. `MockPrinter.files` is read-only; `active_file` identifies only the virtual job. No general replay tool is implemented yet.

## Tests and next steps

```sh
python3 -m unittest discover -s tests -v
```

Tests use ephemeral loopback endpoints and `.tmp/` only. They cover byte-for-byte idle fixtures, both raw and framed profiles, CRC vectors, fragmentation/coalescing, boundary sizes, interrupted/corrupt uploads, commit semantics, explicit start/cancel and persistent jobs **without** a cancel step. Payloads are generated, not copied from the user's model.

The new client's user-run physical upload-only trial has now succeeded through the proxy (CLIENT-UPLOAD-009). Next: record missing queries/client version and separately scope any additional physical job-control tests. A broader reviewed scenario corpus/replay system is planned separately, as is the web interface. Physical-printer tests remain opt-in.
