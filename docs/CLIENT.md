# Print-file upload client

## Status

Implemented as `python3 -m finderlab upload`, with reusable async `FinderClient` in `finderlab/client.py`. Python 3.11+, standard library only. It implements the observed V1.5 block/CRC/ACK protocol, **not** the raw transfer in the old `upload.py`. The client accepts `.gx`, `.gcode` and `.g` (case-insensitive). This is a transfer allowlist, not a guarantee that every format/file is understood or safe to print on physical firmware.

The actual CLI has uploaded the user's `upload/test1.gx` to a fresh ephemeral loopback dummy: 3668165 bytes, 896 blocks, exact received/source content and SHA-256 match, no virtual job started. Independent scripted-server tests check wire bytes against reference replies and a known CRC vector. The user subsequently ran the same client on the host through the proxy to the real Finder: all 896 blocks were acknowledged, final save and control release were confirmed, and client/proxy byte streams matched exactly. No start/stop was sent. See CLIENT-UPLOAD-009 in [PROTOCOL.md](PROTOCOL.md). This validates that upload-only workflow on the observed firmware, not every device/error case or the new client's physical start/stop actions.

The standalone **web** workflow now has a user-requested checked-by-default
start-after-upload option when server job controls are enabled. Its labelled
Save + start click composes two separately recorded sessions after healthy
save/release/finalization; unchecked/legacy API stays save-only. This does not
change CLI defaults or add an implicit client-library start. See
[START_AFTER_UPLOAD.md](START_AFTER_UPLOAD.md).

## Dummy first

Terminal 1 (stop any proxy using the same port first):

```sh
python3 -m finderlab mock --verbose
```

Terminal 2:

```sh
python3 -m finderlab upload upload/test1.gx
```

Default target is `127.0.0.1:8899`. A different port works with `--port`. An ASCII remote filename override is available:

```sh
python3 -m finderlab upload upload/test1.gx --remote-name "client sample.gx"
```

The file must be a nonempty regular `.gx`, `.gcode` or `.g`, at most 8 MiB by default (`--max-file-size` changes this policy). Internal ASCII spaces are allowed in remote names. Paths, control characters, non-ASCII names and ambiguous leading/trailing spaces are rejected. Use an ASCII override if the local basename is incompatible.

Files are sent **unchanged**, including binary GX headers/thumbnails or plain G-code comments/line endings. The local extension is preserved by default; a remote-name override does not convert content. Plain G-code is not automatically wrapped as GX or given a thumbnail. The transport client does not slice, generate GX, inspect model safety, convert formats or fix G-code. Optional CLI slicing is a separate pre-connection Orca stage described below. A `.gx` extension is not proof that its contents are safe or Finder-compatible. Use known-working FlashPrint files for the first physical trial.

## Optional STL slicing before upload

`upload MODEL.stl --slice` uses the separate Orca adapter with explicit `--machine`, `--process`, and `--filament` JSON profiles (`--orca` selects the executable). It slices **before** connecting, retains generated G-code in the run directory and uploads only after successful output validation. Remote names default to the original model stem plus `.gcode`; `.gx` overrides are refused because this does not create a GX container. Plain print-file upload without `--slice` is unchanged; STL cannot accidentally be sent as printer payload.

For offline review use `slice MODEL.stl` instead; it never opens a printer connection. Read [SLICING.md](SLICING.md) for actual commands, profile flattening requirements, limits and unverified native/Finder compatibility. No reviewed Orca profile ships yet, and `--start` is not approval to print unreviewed output.

## What upload does

1. Connect to the explicit endpoint; no discovery or scanning.
2. Claim control (`M601 S1`), check `M115` identifies `Flashforge Finder` / `V1.5 20170419`.
3. Require `M119` to report `READY`; never cancel existing work to make room.
4. Send `M28 <size> 0:/user/<name>` and validate its path/length confirmation.
5. Stream 4096-byte logical blocks with the observed 16-byte header, big-endian fields, CRC32, zero padding and exact indexed ACK checks.
6. Verify that the source has not changed, send `M29`, require `Done saving file.` plus the command echo and final CRLF-terminated `ok`.
7. Try `M602` to release control at a healthy command boundary, then close.

**By default no M23/start or M26/stop is part of uploading.** `--start` is an explicit confirmation to compose upload followed by start, only after verified save and a fresh READY check. No M26 is ever appended. Use an unused remote name to avoid overwriting a file already stored on the printer. No remote existence/listing protocol has been verified, so the client cannot automatically prove the name is unused.

Console progress is **block-acknowledged logical bytes**, separate from final save confirmation. Printed SHA-256 is the source stream hash, not a remote file read-back. Save confirmation is based on the endpoint's reply.

## Optional start after upload

```sh
# Upload only (default):
python3 -m finderlab upload "upload/example.gcode"
# Explicitly request start after confirmed save:
python3 -m finderlab upload "upload/example.gcode" --start
```

Use these first against the **dummy**. `--start` may heat/move a real target, including through a loopback proxy; it is not a motion-safety check. The flag itself supplies confirmation; the separate `start` command still requires `--confirm-start`.

The combined command starts the exact saved destination name, including `--remote-name`, in the same session. Failed block transfer, rejected save or UNKNOWN final-save result never triggers start. If start later fails, the already confirmed file remains saved: the console/save metadata distinguish the stages. Do not blindly re-upload/retry. No automatic stop or cleanup deletion is performed. `.gcode`/`.g` and the combined start mode have been tested locally; the earlier successful physical trial was upload-only with GX, not a guarantee for these additional cases.

## Real-printer trial: preferably through the proxy

Close FlashPrint and keep the physical printer idle and supervised. Start the proxy on the host as described in [PROXY.md](PROXY.md). On that **same host**, run the upload client against its listener, choosing a new remote name:

```sh
python3 -m finderlab upload upload/test1.gx \
  --host 127.0.0.1 --port 8899 \
  --remote-name client-test1-check.gx
```

This loopback command intentionally reaches hardware **through the proxy**. Loopback is not proof of a virtual target. Ensure that `client-test1-check.gx` is not an important existing file; choose another name for repeated experiments.

If the coding environment is containerized, its loopback may not reach a host-side proxy even though capture files are shared. Do not scan for it: run the command on the host or explicitly configure a reachable trusted endpoint.

For direct access to an explicitly chosen printer IP (replace the documentation address):

```sh
python3 -m finderlab upload upload/test1.gx \
  --host 192.0.2.10 --allow-hardware --remote-name client-test1-check.gx
```

Non-loopback addresses require `--allow-hardware`. Targets must be literal IP addresses; only the observed Finder firmware is currently enabled. An agent must still obtain explicit approval for the actual hardware experiment. A first upload-only trial should be checked on the printer's screen and in captures before any start test.

## Separately confirmed actions

```sh
python3 -m finderlab status
python3 -m finderlab start "client sample.gx" --confirm-start
python3 -m finderlab stop --confirm-stop
```

These default to the same loopback endpoint. Use the target/port/hardware flags explicitly as needed. `start` (or upload's explicit `--start`) may physically heat/move the printer; it is **not required to upload**. `stop` cancels current work and is never sent automatically, including on timeout, Ctrl+C, release or disconnect. Default upload-only creates no new print job to stop.

A stop ACK is not proof of READY, stopped motion or cooled heaters; physical firmware has transient states. This is not an emergency-stop facility. Remain at the printer and use its physical controls if necessary.

## Failures and recording

Per-reply/write timeout defaults to 15 seconds; connect timeout 8 seconds; final save timeout 30 seconds. Each reply has a bounded total read deadline, 4096-byte line limit and 64 KiB total reply limit. The incremental reader retains excess bytes, checks complete CRLF lines/command echoes, rejects explicit errors even if followed by `ok`, and requires the exact block index ACK.

There are **no automatic retries/resume**. If a block fails, the connection closes without injecting `M602` into binary payload. After an attempted `M29` without verified final confirmation, the save result is **UNKNOWN**, not success. Start/stop without verified confirmation similarly report unknown job state. Do not blindly retry these operations. Interrupted uploads may leave temporary files/control state requiring manual inspection.

At a healthy command boundary, release is attempted. If release fails after a confirmed save, the save remains confirmed; a separate warning is emitted, not a retry. One client serializes its operations, but there is no cross-process lock: close competing clients before experiments.

Every CLI run prints its private `captures/<run>/` directory. `traffic.log`, structured events and exact request/reply streams are retained, including uploaded model bytes. `mode` is `client`; metadata names the operation and records `start_requested`, plus `upload_confirmed` / `start_acknowledged` when those stages succeed. File/name validation errors now create an error with phase `preflight` before any endpoint connection. Invalid CLI syntax/configuration can still fail before a capture can be initialized. See [CAPTURES.md](CAPTURES.md). Original print-file examples under `upload/` or `uploads/` remain ignored by Git. No original model content is committed as a regression fixture.

## Later, not this step

Slicer invocation, FlashPrint-compatible start/end/coordinate behavior, GX packaging and embedded thumbnails are separate future stages. The user's reported PrusaSlicer collisions make semantic/motion compatibility a hardware-test blocker, not something a binary GX wrapper can solve. See [ROADMAP.md](ROADMAP.md).
