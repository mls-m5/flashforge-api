# Persistent traffic logs and connection history

## Implemented behavior

The `mock`, `proxy`, offline `slice`, and client commands (`upload`, `status`, `start`, `stop`) record by default. Every invocation creates a new private subdirectory under `captures/`, printed at startup. Every accepted or outgoing session gets its own ID and two raw streams. Client manifests use mode `client` and include the operation in metadata. Restarting the program never overwrites older runs.

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

`events.jsonl` contains the same observations in a machine-readable form. `manifest.json` records mode, tool version, host OS, configuration, optional FlashPrint/experiment metadata, recording limits and final session summaries. Each summary includes close reason, raw stream sizes and SHA-256 hashes. Client metadata also records `start_requested`, `upload_confirmed` and `start_acknowledged` as applicable, so a saved file and a later start failure are not conflated.

Client file/name validation now happens after recorder initialization but **before connecting**. Its failures appear as `error` events with phase `preflight`, normally with no sessions/raw streams. Other client phases include `connect`, `upload` and `start_after_upload`. CLI syntax/configuration errors can still fail before a recorder is initialized; an unwritable capture location cannot create a log.

The initial manifest has `complete: false`. It is finalized on orderly shutdown (including Ctrl+C). You can inspect the logs while the process is running, but final hashes/session summaries appear at shutdown. `complete` describes **the recording**, not whether a connection, upload or print succeeded. A recorded refusal or timeout can still be a complete recording.

Tell the assistant the printed capture path when it exists in the same accessible workspace. No remote log collection or automatic external upload is implemented. Recordings on another computer must be copied into the workspace or otherwise shared deliberately.

## Passive status reader

`finderlab/passive_status.py` derives M105/M119/M27 metrics from existing proxy
server streams and corresponding event offsets/timestamps, without altering
recordings or querying hardware. The web source is startup-configured; HTTP
cannot supply paths. Tail reads are bounded, incomplete frames/JSON are not
rewritten, and timestamps are observation times rather than page-fetch times.
Freshness is per metric and session, not inferred from a growing file or
manifest completeness. The page marks unknown/stale/partial data explicitly.
See [STATUS.md](STATUS.md) for source matching, tail limits and privacy. Status
view refresh produces no new printer capture/session.

## Standalone web recordings

The standalone page creates a separate `web-data/captures/<run>/` per explicitly
requested Slice, Save or optional Start/Cancel, reusing format v1 (`slice`/`client`). Metadata includes
`interface: standalone-web`, operation and `start_requested` (true only for an
explicit Start). Separate `start_acknowledged`/`stop_acknowledged` markers record
parsed job-command acknowledgements, not physical motion/thermal state. Browser
file receipt alone makes no printer session; files stay in its private single
slot. The page displays a bounded 4000-character Orca diagnostic excerpt, not a
replacement for raw capture output. Captures are retained after explicit slot
discard and count toward the workbench's conservative 256 MiB storage admission
budget. Interrupted runs are never resumed automatically. See [WEB.md](WEB.md)
for workspace quotas, native scratch limits and shutdown/unknown outcomes.
Owned-dummy web tests also record `target_kind: owned_dummy` and an emulated
model label; ordinary configured endpoints remain `configured_endpoint` (not a
claim that a loopback endpoint is virtual). The owned dummy's files are RAM-only;
web/client captures still preserve the transferred model bytes. Neither runtime
volumes nor these raw captures belong in Git.

## Virtual manual-control intents (no network sessions)

Owned-dummy manual rehearsal creates mode`manual-virtual`, operation
`manual_virtual`, metadata`wire_commands_sent:false` captures in the web
workspace. `manual_virtual_intent` records the typed intent, previous state and
a candidate snapshot before commit. Capture finalization must succeed before
counter/light state changes; a persisted intent alone does not prove a commit
if recording failed/the process crashed. No G-code/physical actions or raw
sessions are generated. Each action has64KiB recording bound and conservative
workspace admission; accumulated runs/entry count remain bounded by existing
web quota. Rejected validation/stale/busy/locked actions create no new capture.
File discard does not discard captures or reset counters. These are synthetic
UI-policy records, not protocol evidence. See MANUAL_CONTROLS.md.

## Active status monitoring recordings

A started monitor writes a separate mode`client` capture under the web workspace,
metadata operation`monitor`, interface`standalone-web`, target kind and fixed
interval. Startup monitoring is default only in the deliberate proxy/owned-dummy
launchers, not the passive watcher/offline slicer or raw web CLI. One session
is retained across batches, released before local printer jobs, and may be
reopened after a successful operation. Errors/uncertain I/O stop monitoring
rather than retrying. Raw streams remain authoritative; session-associated
`status_snapshot` events contain bounded parsed values and `batch_completed_utc`
(completed response-batch time, not physical-event time). Active status GETs
read the in-memory cache and add no commands/events by themselves. Captures are
64MiB/256 sessions per run, retain prior runs and count toward web workspace
admission; remaining monitor budget is reserved alongside foreground jobs.
Stop polling finalizes this capture, never cancels printing. See STATUS.md.

## Slicer diagnostics and generated files

Standalone slicing uses mode `slice` with no printer sessions; combined `upload --slice` keeps mode `client`. `slicer_command`, `slicer_output`, `slicer_exit` and `slicer_result` events describe capability probing, slicing argv, stdout/stderr bytes (authoritative `data_hex`, plus readable derived text), completed exit codes and candidate output hashes. The manifest retains input hashes/basenames, limits, executable path and `slicing_confirmed` when completed. Errors in phase `slicing` stop before any printer connection. `slicer_result` is not a toolpath safety assertion or proof that output publication/upload later succeeded.

`slicer_settings` records the normalized typed quality options, actual allowlisted
process changes, original process hash and effective process hash/quality values.
The same fields are retained in manifest metadata. `slicing_inputs.process`
still hashes the original server-owned snapshot; it is **not** silently
relabelled as the modified version. `effective_process_sha256` hashes the
bytes actually passed to Orca. No overrides means identical original/effective
bytes. Original profiles and all machine/filament/start/end/retraction settings
are not edited. `xy_hole_compensation`, when selected, records a bounded per-edge
process override; omitted/null preserves the profile, explicit0 disables it.
The independent `xy_contour_compensation` field uses the same typed bounds /
profile behavior. Effective quality records both applied offsets. Negative
contour shrinks outer boundaries; positive hole enlarges openings.
These fields describe the artifact, not measured print dimensions or a global
calibration. See HOLE_COMPENSATION.md for native offline evidence. Settings
capture improves reproducibility, not print safety.

Generated `sliced.gcode` is retained under the run directory by default, or at standalone slice's explicit `--output`. It has a **separate** size bound (`--max-file-size`) and is outside `--max-capture-bytes`; original profiles/model snapshots and native temporary data are cleaned from project-local `.tmp/`. Raw slicer log chunks are bounded independently and count toward the existing event/log quota. Full details and trust limits: [SLICING.md](SLICING.md).

## Offline numerical review reports

`python3 -m finderlab review FILE` reads a bounded regular G-code file (or the
observed GX body offset) and writes a derived JSON report to stdout. It creates
no printer session or capture, runs no slicer and does not rewrite its source.
Reports include hashes/coordinates and may disclose private geometry; keep
reports from private files in ignored `.tmp/` or local profile storage. Modal/
E-origin assumptions and unmodeled homing remain explicit. Empty alerts do not
certify motion safety or firmware compatibility. See
[ORCA_FINDER_DRAFT_02.md](ORCA_FINDER_DRAFT_02.md) for actual native trials and
how the new diagnostic differs from preserved raw evidence.

## Format version 1

`client` is the incoming client (usually FlashPrint) for proxy/mock captures, or the new upload application for mode `client`; `server` is the selected target/mock in all cases. Raw files contain the concatenated observed bytes for that session/direction, not PCAP packets.

Event types currently emitted:

- `listener_bound`: actual local endpoint, including an ephemeral port if requested;
- `connection_open`: session ID, incoming peer/local endpoints, proxy target when applicable;
- `target_connected`: proxy upstream connection established;
- `data`: direction, stream offset, length, escaped preview and truncation flag;
- `forward_complete`: reference to the `data` event after outgoing `drain()` succeeds;
- `eof`: direction of observed EOF;
- `error`: phase and error type, with a message where available;
- `connection_close`: session close reason;
- `capture_end`: orderly recorder finalization;
- `status_snapshot`: optional active-monitor parsed status batch with completion timestamp (raw stream still authoritative);
- `manual_virtual_intent`: synthetic owned-dummy control intent/before/candidate, no wire command and not physical-motion evidence;
- `slicer_settings`, `slicer_command`, `slicer_output`, `slicer_exit`, `slicer_result`: optional Orca stages described above.

Each event includes `v`, monotonically increasing `seq`, `session_id` (or null for run-level events), UTC timestamp and `monotonic_ns` elapsed since capture start. Sequence order is logging order, not proof of causality between simultaneous directions.

A data event records bytes the application read, or generated for outgoing client requests/mock replies. It does not prove the peer received or accepted them. `forward_complete` means a transport write/drain completed without a known error; it does not prove the remote application processed the data. On write failure, already forwarded byte count may be unknown.

A socket read is not a protocol message or a TCP packet. Proxy recordings include only bytes the relay actually read: data still buffered by the OS when a connect failure/shutdown occurs may not appear. Mock parsing happens after recording, so partial/invalid commands and binary payloads that were read are retained.

The recorder itself does not infer command success; the new client parses its own replies separately. PCAP export, general protocol decoding, replay and a standalone capture validator remain unimplemented. Hashes and offsets are checked in automated tests. A separate host packet capture is useful for transport-level verification.

## Limits and failure behavior

Defaults:

- `--max-capture-bytes 268435456`: 256 MiB **per run**, shared by raw streams, JSON events and the human log;
- `--max-sessions 1000`: server-mode maximum recorded sessions per run, bounding manifest/history metadata (a client invocation makes one session);
- active clients and connection timeouts are limited separately by the mock/proxy configuration.

The manifest and small filesystem metadata are outside the byte counter. Repeated runs accumulate: there is **no automatic deletion, rotation or total-directory quota**. Review disk space and manually archive/delete old runs as appropriate.

On quota exhaustion or recording I/O failure, the affected connection stops rather than silently forwarding unrecorded data. The CLI then shuts down and reports the incomplete capture. Already forwarded bytes cannot be recalled; a partial file or uncertain operation may remain on a real printer. Recording failures prevent a `complete: true` result. If final manifest writing itself fails, the previous incomplete manifest remains.

Writes are flushed to local files without waiting for shutdown, but not `fsync`ed per event: this is not a power-loss-safe audit log. Disk writes are synchronous and can add latency; the proxy promises byte preservation, not identical packet segmentation or timing. A crash can leave incomplete final JSON/raw data; never treat such a run as complete.

## LAN credentials versus printer captures

Opt-in LAN sharing (LAN.md) uses a new random Basic password printed only to
the foreground server console. It is not a CLI argument, API config value,
profile, printer command or printer/slicer capture field. HTTP Authorization
headers are not recorded. The console itself is sensitive: do not share a
terminal transcript/screenshot containing the password. Basic over HTTP is
unencrypted and network observers can still obtain credentials/model bytes;
these capture-format choices do not provide transport encryption. All logged-in
users can access the shared current artifact; private captures still have no
HTTP download route.

## Privacy and sharing

Recordings can contain full uploaded models, filenames, serial numbers, IP/MAC addresses and every command sent. A mock's virtual storage is RAM-only, but **its capture files persist payload bytes on disk**. The run directory is created with private permissions where supported; also secure its parent directory and backups.

Do not commit raw captures or share them automatically. Prefer a small model you own when collecting a reference. Keep originals unchanged; make separate reviewed derivatives for sharing and document changes. Binary-field edits can invalidate lengths, offsets and hashes.

Only small, reviewed fixtures with provenance and appropriate permission belong in `tests/fixtures/`. `docs/traces/` contains deterministic, human-readable derivatives generated only from two pinned, previously reviewed fixtures by `tools/export_reviewed_traces.py`; it is not generated from private raw captures. Verify with `python3 tools/export_reviewed_traces.py --check`. If a source fixture hash changes, the exporter refuses to proceed; conduct a new privacy review and intentionally update the pinned hash before generating new derivatives. The upload transcript omits original payload bytes and is not replayable. Runtime test data belongs in `.tmp/` and is cleaned up by the tests.
