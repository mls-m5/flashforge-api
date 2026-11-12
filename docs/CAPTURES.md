# Persistent traffic logs and connection history

## Implemented behavior

Both CLI modes (`mock` and `proxy`) now record by default. Every invocation creates a new private subdirectory under `captures/`, printed at startup. Every accepted session gets its own ID and two raw streams. Restarting the program never overwrites older runs.

```text
captures/<UTC-start>-<random-id>/
  manifest.json
  traffic.log
  events.jsonl
  sessions/s0001/
    client-to-server.bin
    server-to-client.bin
  sessions/s0002/
    ...
```

`--capture-dir PATH` changes the parent directory. Default `captures/` is ignored by Git. If you choose a different location, keep it out of version control yourself. Test-generated recordings and other temporary files use the ignored project-local `.tmp/`, not system temporary storage.

## Reading logs

Start with **`traffic.log`**: UTC timestamps, session IDs, connection lifecycle, data directions, escaped byte previews and errors. Data previews include at most 256 bytes per observation. Large or coalesced messages can exceed the preview; the `.bin` files preserve the full bytes, without text conversion. Previews are not a substitute for the raw stream.

`events.jsonl` contains the same observations in a machine-readable form. `manifest.json` records mode, tool version, host OS, configuration, optional FlashPrint/experiment metadata, recording limits and final session summaries. Each summary includes close reason, raw stream sizes and SHA-256 hashes.

The initial manifest has `complete: false`. It is finalized on orderly shutdown (including Ctrl+C). You can inspect the logs while the process is running, but final hashes/session summaries appear at shutdown. `complete` describes **the recording**, not whether a connection, upload or print succeeded. A recorded refusal or timeout can still be a complete recording.

Tell the assistant the printed capture path when it exists in the same accessible workspace. No remote log collection or automatic external upload is implemented. Recordings on another computer must be copied into the workspace or otherwise shared deliberately.

## Format version 1

`client` is the incoming client (usually FlashPrint); `server` is the proxy target or the mock. Raw files contain the concatenated observed bytes for that session/direction, not PCAP packets.

Event types currently emitted:

- `listener_bound`: actual local endpoint, including an ephemeral port if requested;
- `connection_open`: session ID, incoming peer/local endpoints, proxy target when applicable;
- `target_connected`: proxy upstream connection established;
- `data`: direction, stream offset, length, escaped preview and truncation flag;
- `forward_complete`: reference to the `data` event after outgoing `drain()` succeeds;
- `eof`: direction of observed EOF;
- `error`: phase and error type, with a message where available;
- `connection_close`: session close reason;
- `capture_end`: orderly recorder finalization.

Each event includes `v`, monotonically increasing `seq`, `session_id` (or null for run-level events), UTC timestamp and `monotonic_ns` elapsed since capture start. Sequence order is logging order, not proof of causality between simultaneous directions.

A data event records bytes the application read (or, for mock replies, generated). It does not prove the peer received or accepted them. `forward_complete` means a transport write/drain completed without a known error; it does not prove the remote application processed the data. On write failure, already forwarded byte count may be unknown.

A socket read is not a protocol message or a TCP packet. Proxy recordings include only bytes the relay actually read: data still buffered by the OS when a connect failure/shutdown occurs may not appear. Mock parsing happens after recording, so partial/invalid commands and binary payloads that were read are retained.

No per-command success inference, protocol decoding, PCAP export, replay or standalone capture validator is implemented yet. Hashes and offsets are checked in automated tests. A separate host packet capture is useful for transport-level verification.

## Limits and failure behavior

Defaults:

- `--max-capture-bytes 268435456`: 256 MiB **per run**, shared by raw streams, JSON events and the human log;
- `--max-sessions 1000`: maximum recorded sessions per run, bounding manifest/history metadata;
- active clients and connection timeouts are limited separately by the mock/proxy configuration.

The manifest and small filesystem metadata are outside the byte counter. Repeated runs accumulate: there is **no automatic deletion, rotation or total-directory quota**. Review disk space and manually archive/delete old runs as appropriate.

On quota exhaustion or recording I/O failure, the affected connection stops rather than silently forwarding unrecorded data. The CLI then shuts down and reports the incomplete capture. Already forwarded bytes cannot be recalled; a partial file or uncertain operation may remain on a real printer. Recording failures prevent a `complete: true` result. If final manifest writing itself fails, the previous incomplete manifest remains.

Writes are flushed to local files without waiting for shutdown, but not `fsync`ed per event: this is not a power-loss-safe audit log. Disk writes are synchronous and can add latency; the proxy promises byte preservation, not identical packet segmentation or timing. A crash can leave incomplete final JSON/raw data; never treat such a run as complete.

## Privacy and sharing

Recordings can contain full uploaded models, filenames, serial numbers, IP/MAC addresses and every command sent. A mock's virtual storage is RAM-only, but **its capture files persist payload bytes on disk**. The run directory is created with private permissions where supported; also secure its parent directory and backups.

Do not commit raw captures or share them automatically. Prefer a small model you own when collecting a reference. Keep originals unchanged; make separate reviewed derivatives for sharing and document changes. Binary-field edits can invalidate lengths, offsets and hashes.

Only small, reviewed fixtures with provenance and appropriate permission belong in `tests/fixtures/`. Runtime test data belongs in `.tmp/` and is cleaned up by the tests.
