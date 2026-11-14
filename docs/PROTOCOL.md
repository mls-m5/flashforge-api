# Protocol evidence and open questions

This is a working journal, **not a complete Finder 2 specification**. A user-collected real-printer proxy capture now establishes a connection/idle baseline; see FINDER-IDLE-003 below. Behaviors outside the observed exchanges remain unverified.

## Implemented profiles

The default `finder-v1.5` combines captured connection/idle replies with observed block upload and job-command reply formats. Name/serial are anonymized. `finder-v1.5-idle` retains the earlier connection-only profile with experimental raw upload; `synthetic-v1` retains the original mock. See [MOCK.md](MOCK.md) for scope. Errors, release/control policy, listing and virtual job dynamics are still mock conventions. The original `upload.py` is incompatible with the framed upload now observed on this printer.

## FINDER-IDLE-003 — Real-printer connection and status baseline

Source: `captures/20261112T190818Z-31ded6e5f0a5`, session `s0001`, starting 2026-11-12 19:08 UTC. User-reported model: Finder 2. Observed identity: `Flashforge Finder`, firmware `V1.5 20170419`. FlashPrint version and selected machine profile are unknown. The manifest has subsequently been finalized successfully.

Observed sequence: `M601 S1 → M115 → M650 → M115 → M114 → M27 → M119 → M105`, then sustained status polling. The client's repeated `M115` is therefore also present in a successful real-printer session and is not itself a failure indicator.

Important differences from `synthetic-v1`:

- `M601`: `Control Success.` (no `V2.1` suffix).
- `M115`: machine type has no `2`; real firmware text; two spaces between axis dimensions; no MAC field.
- `M650`: `X: 34 Y: 0`.
- `M114`: integer coordinate formatting.
- `M119`: `Z-max`, different endstop/status values and field order; no LED/current-file lines.
- `M105`: `T0:21 /0 B:0 /0` in the selected idle baseline.

The reviewed fixture `tests/fixtures/finder-v1.5-idle.json` contains the first 14 complete exchanges: client bytes `[0,98)`, server bytes `[0,1076)`. Only name and serial were replaced, preserving lengths. It was compared offline to the actual raw ranges with those two substitutions. Raw captures/private identifiers are not committed. See `tests/fixtures/README.md` for provenance and sanitized hash.

This is evidence for the observed responses, not for arbitrary error handling, control conflicts, release, upload, discovery or timing requirements. Snapshot temperatures/endstops are not a dynamic physical model.

## FINDER-MOCK-004 — FlashPrint accepts the updated idle profile

User-reported successful connection, supported by `captures/20261112T191332Z-4bda35d1b451`, session `s0001`, 2026-11-12 19:13 UTC. The finalized capture uses `finder-v1.5-idle` with the anonymized name/serial.

The client sent 57 commands: one control claim, two identity queries, one offset query, one position query, and 52 status queries (`M27`: 17, `M119`: 18, `M105`: 17). Every command has a corresponding successful reply; no error events or error replies were recorded. Polling lasted about 17 seconds until recording shutdown (`capture_shutdown`), rather than the previous immediate release/disconnect. Raw stream sizes and hashes match the manifest.

This validates manual connection and idle polling in the user's setup (FlashPrint version still unknown), not uploads or printing. No single field has been isolated as the cause of the earlier failure.

## FINDER-UPLOAD-005 — Framed upload, explicit start and cancel

Source: `captures/20261112T191450Z-2b04f784b894`, session `s0001`, 2026-11-12 19:15 UTC. Same observed machine type and firmware as FINDER-IDLE-003. The user reports saving a file, starting the job and aborting it. FlashPrint version remains unknown. The following complete transfer interval was inspected offline; the full recording was still unfinalized at inspection.

The client sent `M28 102989 0:/user/<name>.gx`, then **26 frames of 4112 bytes**, then `M29`, then **separate** `M23` start and later **separate** `M26` cancel. No `M24` was sent in this workflow. Filename in checked-in examples is anonymized to `test_box.gx`.

Wire data interval: client bytes `[745,107657)`, totaling 106912 bytes. Each frame:

| Offset | Length | Meaning |
| --- | --- | --- |
| 0 | 4 | Magic bytes `5a 5a a5 a5` |
| 4 | 4 | Zero-based block index, unsigned big-endian |
| 8 | 4 | Logical file-byte count in this block, unsigned big-endian |
| 12 | 4 | CRC32 of **logical payload bytes only**, unsigned big-endian |
| 16 | 4096 | Payload plus zero padding to fixed wire size |

All 26 headers, indexes, CRCs and padding were checked against the actual raw bytes. Logical lengths were 4096 for blocks 0–24 and 589 for block 25; last-block padding was 3507 zero bytes. CRC matches Python `zlib.crc32` over unpadded data, not the header or padding. Reconstructed logical byte count equals the advertised 102989. All block acknowledgements were `N<index> ok\r\n`, indexes 0–25.

Captured reply bodies (standard `CMD ... Received.` / `ok` envelope):

- `M28`: `Writing to file: 0:/user/test_box.gx  Length: 102989` (two spaces before `Length`).
- `M29`: `Done saving file.`
- `M23`: `File opened: 0:/user/test_box.gx Size: 102989`, then `File selected`.
- `M26`: no additional body.

After `M23`, status became `BUILDING_FROM_SD`, first `HOMING`, later `WAIT_ON_TOOL`; the temperature target was 220. After `M26`, intermediate `PAUSED`/building status appeared before `READY` and a zero target. These transitions are observations, not proof of safe emergency-stop behavior. Actual execution progress used a denominator of 88477 rather than the GX file size 102989; interpreting GX headers/execution offsets remains open.

Implementation: `finder-v1.5` validates the captured framing and returns ACKs, saves only on `M29`, starts a **virtual** job only on `M23`, and cancels only on `M26`. There is no automatic print-start, abort, timed completion, motion or heating. Virtual active status uses representative captured shapes; progress stays zero over logical file size. Thermal/homing/cancel transients are not replayed. Release/disconnect does not cancel a virtual job.

Limits of this initial observation: one successful file-transfer capture; FINDER-UPLOAD-006 below adds a second, larger transfer. Neither establishes all sizes/firmware variants. Bad-CRC handling/retries were not observed; the mock deliberately errors and closes rather than inventing retransmission behavior. It requires the observed full-block/final-block lengths and zero padding. The existing raw uploader does **not** implement this framing or ACK format and remains unchanged.

`tests/fixtures/finder-v1.5-upload.json` stores reviewed framing facts and command/reply frames, not model content. Tests generate deterministic payloads, include an independent CRC32 test vector and separately test upload-only, start-without-cancel, and explicit cancel. A broader sanitized trace corpus and reusable replay tooling are planned, not implemented by these tests.

## FINDER-UPLOAD-006 — Larger transfer independently confirms CRC/framing

Source: finalized proxy capture `20261112T193539Z-f39c040f886a`, session `s0001`, 2026-11-12 19:35–19:40 UTC. Observed firmware remains `V1.5 20170419`; FlashPrint version is unknown. Both raw stream sizes/SHA-256 and all event byte ranges match the manifest. The complete client stream was parsed without unexplained bytes.

| Check | Result |
| --- | --- |
| Advertised/logical file size | 3668165 bytes |
| Upload wire interval | Client `[2237,3686589)`, 3684352 bytes |
| Frames | 896 × 4112 bytes |
| Indexes | Exactly 0–895, no duplicates/gaps; crosses the 255 boundary |
| Logical lengths | 4096 for blocks 0–894; 2245 for block 895 |
| Last padding | 1851 zero bytes |
| CRC32 over logical data | **896/896 match** |
| CRC32 including the 12 header bytes before the CRC field | **0/896 match** |
| Final CRC32 including padding | Does **not** match the stored CRC |
| ACKs | Exactly `N0 ok` through `N895 ok`, in order |
| Error/resend replies or recorder errors | None |

The existing big-endian header / unpadded-data CRC32 hypothesis therefore needs no change. This independently confirms the same framing on two differently sized real files (922 verified blocks in total), including a different final-block length. It still does not establish behavior on corrupt/missing blocks, retries or other firmware.

Command sequence remains explicit: `M28` at 19:37:44.036 UTC, `M29` at 19:39:14.398, `M23` at 19:39:14.622, and `M26` at 19:39:22.083. Save/start/cancel reply shapes match FINDER-UPLOAD-005. No `M24`/`M25` or automatic stop command appears in the transfer. Stop is a later client command, not a required upload suffix.

**New finding:** the actual filename contains spaces and hyphens. The printer accepts the complete remainder of `M28 <size> <path>` and `M23 <path>` as a path, without quotes. The original mock's generic whitespace splitting/name restriction was too strict. The framed profile now preserves internal spaces (including repeated spaces), while retaining its bounded ASCII/path/control-character safety policy. Legacy raw profiles keep their earlier no-space policy. The private filename and model bytes are not committed.

A compact `larger_transfer` entry in `tests/fixtures/finder-v1.5-upload.json` retains framing facts and source ranges. The regression test uploads generated content at the observed size with a synthetic spaced filename, checks all 896 ACKs, and verifies exact filename lookup/start without an implicit cancel. This is a local mock test, not replay of the private model or a new hardware test.

## FINDER-MOCK-007 — FlashPrint transfer/start/cancel against the dummy

Finalized mock capture `20261112T194950Z-63207ef4669d`, session `s0001`, uses `finder-v1.5`. User reports the dummy trial working. Client commands include one 3668165-byte `M28` upload, `M29`, separate `M23`, later `M26`, and 105 each of `M27`, `M119`, `M105`. The recording also contains one `G91` request (motion-related commands remain unsupported by deliberate mock policy). This is evidence for the observed file/job workflow, not every FlashPrint UI operation, physical dynamics or hardware safety. Client version remains unknown.

## CLIENT-UPLOAD-008 — New upload CLI, provided GX, fresh dummy

Actual application trial: `python3 -m finderlab upload upload/test1.gx` targeted a newly started dummy on an ephemeral loopback port, **not** the user's existing listener/proxy. Client capture `20261112T201030Z-a4de769f3bb2`, dummy capture `20261112T201030Z-56895924baa7`, experiment `provided-gx-client-dummy`. Both recordings were finalized.

The file was 3668165 bytes; the dummy received 896 framed blocks, saved the file, and its exact bytes/SHA-256 matched the original (including existing binary GX/preview data). The wire command sequence was `M601 S1 → M115 → M119 → M28 → M29 → M602`. **No M23/start or M26/stop was sent**, and no virtual job became active. Original model bytes/file hashes are not added to Git.

New client implementation is separate from unchanged `upload.py`. It checks the observed machine type/firmware, requires READY for upload/start, checks exact block ACK indexes, and requires a complete command echo / final save body / CRLF-terminated `ok`. It performs no blind retry or automatic start/cancel. During a failed binary transfer, close instead of injecting a cleanup command into expected payload. Missing final save confirmation reports UNKNOWN rather than success. See [CLIENT.md](CLIENT.md).

Independent scripted-server tests use the reviewed reply frames and a standard CRC vector, not just a mutually agreeing mock/client encoder. Generated-payload and CLI tests also cover failure/cancellation cases. These tests do not prove that minimal handshake, release behavior or timing work against physical firmware; the next planned trial at that point was an explicitly approved upload-only run through the host-side proxy, subsequently completed in CLIENT-UPLOAD-009. The coding environment's loopback did not expose that proxy, so the agent did not attempt a hardware connection. A host-side command is documented separately.

## CLIENT-UPLOAD-009 — Host-side client uploads to real printer through proxy

The user started a host-side proxy and ran the new client manually after the agent confirmed that the host's loopback listener was not exposed inside the coding environment. No physical connection was made by the agent. Finalized client capture: `20261112T201621Z-f246bc35b6d3`, session `s0001`; proxy capture: `20261112T201223Z-6d126b24ea19`, matching session `s0001`. Transfer window: 2026-11-12 20:16:21–20:18:21 UTC; observed firmware `V1.5 20170419`.

- Source GX: 3668165 bytes, 896 framed blocks, ACKs `N0` through `N895`.
- Existing production decoder validates all recorded frames; reconstructed logical bytes match the provided `upload/test1.gx` exactly.
- Client and proxy raw streams are byte-identical in **both directions**; the client manifest's raw lengths/hashes match.
- Command sequence: `M601 S1 → M115 → M119 → M28 → M29 → M602`. No `M650`/`M114` prerequisite was needed in this successful minimal client workflow.
- `M29` reply: `CMD M29 Received.\r\nDone saving file.\r\nok\r\n`.
- `M602` reply: `CMD M602 Received.\r\nControl Release.\r\nok\r\n` (the release success shape is now directly observed, not just a mock convention).
- No client errors, automatic retries, `M23` or `M26`. No fixed pre-M29 sleep was used by this client.

This supports successful save/release on the observed hardware/firmware and file. It is not remote file read-back/hash verification, a printer-screen/preview check, a hardware emergency-stop guarantee, or validation of unrelated slicer output. No new-client start/stop command was tested physically in this trial. Original file, name/hash details and raw recordings remain outside Git.

## CLIENT-OPTIONS-010 — File allowlist, explicit start and diagnostics

User requested plain G-code transfer and an explicit upload-and-start flag. The client now allows `.gx`, `.gcode` and `.g`, preserving bytes/default extension without interpreting, converting or validating toolpaths. This allowlist is not new evidence that every extension is physically printable on the firmware.

The existing newest pre-change recordings were proxy `20261112T221825Z-06ea748aad87` and client `20261112T221858Z-7faf5e3f4d55`. They show a **GX** transfer with blocks 0/1 acknowledged and block 2 sent, then client `CancelledError`; no M29 or M23. They do not show a `.gcode` rejection by the printer. Old extension rejection happened during local preflight before capture initialization. Preflight file/name errors are now logged before any endpoint connection, without changing CLI syntax/configuration guards.

Local development trial for the new options: supplied 36176-byte `.gcode` sent via the actual CLI to a fresh ephemeral dummy, saved byte-for-byte and explicitly started as a virtual job with `--start`. Client capture `20261112T235709Z-ae02c8614f60`, dummy capture `20261112T235709Z-ce09a7299b86`, experiment `gcode-start-dummy-only`. Wire sequence: `M601 S1 → M115 → M119 → M28 → 9 frames → M29 → M119 → M23 → M602`. No M26 was sent and no physical printer was contacted.

The upload flag is explicit confirmation, not a new default. M23 uses the actual saved remote basename (including overrides) only after verified M29 and a fresh READY check. Wrong ACK, failed/unknown save or a non-READY post-save state cannot trigger start. An uncertain start is not retried; the preceding confirmed save remains recorded separately. Tests cover these failure gates plus default upload-only behavior and invalid-format logging with no connection.

These local checks do not validate physical plain-G-code support, the user's new Prusa toolpaths, or the optional combined workflow on hardware. Earlier successful physical client evidence (CLIENT-UPLOAD-009) remains an upload-only GX trial.

## SLICER-ADAPTER-011 — Optional Orca orchestration, no new hardware evidence

User requested on-demand STL slicing before upload. `slice` and upload `--slice` now orchestrate a trusted external Orca CLI, with required explicit JSON profiles, isolated input snapshots, bounded process/log/output resources and diagnostics. The uploader connects only after successful slicing and default operation still sends no M23/M26. Profile/toolpath safety, GX generation and firmware acceptance are not inferred.

External interface references and exact flags are recorded in [SLICING.md](SLICING.md). At initial adapter implementation, native Orca was **unknown/not installed** here. Local tests use an independent fake executable, then fresh ephemeral `finder-v1.5` dummies for byte preservation, stage ordering and opt-in virtual start. They are orchestration regression checks, not actual slicing or new independent Finder protocol evidence. No physical printer was contacted. A subsequent approved runtime installation enabled a native help-only probe of the official 2.3.0 asset under adapter limits: capture `20261113T212359Z-e2569f3cc60a`, experiment `orca-native-help-only`, no printer sessions. Required flags are advertised; the literal banner is `OrcaSlicer-01.10.01.50:` despite the release asset's 2.3.0 name. This is CLI capability evidence only, not actual slicing or Finder compatibility. See [ORCA_INSTALL.md](ORCA_INSTALL.md). The next acceptance step remains an offline native/profile slicing trial with logs/output shared for review.

## SLICER-DRAFT-012 — Local edited copy, native option rejection

User-requested local profile copies are documented in [ORCA_FINDER_DRAFT_01.md](ORCA_FINDER_DRAFT_01.md). They are ignored private derivatives, not approved printer profiles. Three native offline mode-`slice` trials on a generated review cube are captured as `20261114T091222Z-53559609ef80`, `20261114T091308Z-2216cf6d8b75` and `20261114T091406Z-47664b67deca`. After correcting standalone CLI compatibility metadata, the last trial rejects `gcode_flavor: invalid value sailfish` before generating G-code. No printer sessions or hardware commands occurred.

This is native Orca 2.3.0 configuration evidence, not Finder protocol evidence. The tagged 2.5.0 source also excludes Sailfish from accepted values; existence of its enum key was insufficient evidence of support. Retain this blocker rather than silently switching to Marlin. The earlier Sailfish comparison choice came from the supplied Prusa configuration and is not independent proof of the physical printer's required dialect. A separately scoped offline compatibility investigation is needed before changing that choice.

## SLICER-DRAFT-013 — Explicit offline Marlin-emission experiment

User authorized a separate offline candidate, not a firmware change or printer
trial. Native Orca 2.3.0 now generates cube/holder output with private draft 02;
all five CLI captures under `captures/finder02/` finalized with zero printer
sessions. See [ORCA_FINDER_DRAFT_02.md](ORCA_FINDER_DRAFT_02.md) for exact IDs and
stages. Stage B exposed mixed-XYZ travel with nominal Z component12.915967 mm/s;
stage C's separate layer Z step yields resolved nominal components at most7 mm/s
in both current files. Final requested E delta is -1.3 mm, with no extra custom
end E/XY/Z park; the old +363 mm E-only end discontinuity is not present.

Native HTTP Slice/download capture
`web-data/finder02-native/captures/20261114T144346Z-167968ea37f7` likewise has no
printer sessions, with Save/job controls disabled. These are numerical/native
application observations, **not hardware protocol or collision-safety evidence**.
G21/M82 are added versus the working FlashPrint command set, M118 is omitted,
and homing/offset/clearance/material semantics remain unresolved. Source draft01
and mounted profiles are unchanged; no generated candidate was uploaded/started.

## FINDER-MANUAL-017 — User FlashPrint control actions, static log inspection

The user reports controller/servo on/off, LED, extruder forward/reverse/stop,
and XYZ actions. Running proxy capture`20261114T194822Z-b991640f7b31`, s0001,
contains G91/M17/M18/M116/M117/M146, decimal-comma G1 E/XYZ requests and M112
stop requests interleaved with status polling. Manual ACKs frequently end in
LF-only`ok\n`, unlike status/M112 CRLF. See
[MANUAL_CONTROLS_CAPTURE.md](MANUAL_CONTROLS_CAPTURE.md) for timestamps,
byte ranges, evidence limits and safety questions. No replay, new hardware
connection, parser change or motion API is introduced. Large relative targets
are not a small-step implementation or emergency-stop specification.
A later owned-dummy-only [manual panel](MANUAL_CONTROLS.md) now rehearses typed
intents with bounded counters and a synthetic warm flag. It sends no wire
commands, changes no parser/TCP mock replies and supplies no independent
physical small-step/thermal/limit evidence. Configured printer/proxy controls
remain locked; this does not clear the missing evidence above.

## FINDER-START-016 — User physical cube startup, no collision reported

The user reports starting the Orca-generated cube on the physical Finder2 and
observing no startup collision. Host web captures
`20261114T194200Z-3eaa5f777f9e` (slice),
`20261114T194203Z-aaae4cb7f728` (confirmed save), and
`20261114T194209Z-0fa308f10bca` (confirmed start), under
`web-data/proxy-test/captures/`, all finalized. The last two share the same
save identity and exact `cube-20x20x5.gcode` destination. Start commands:
M601/M115/M119/M23/M602; fresh READY and file size76579 confirmed. No automatic
M26 was appended. Firmware reports V1.5 20170419; generated output uses the
host Orca2.5 build/current private draft02; nozzle0.4 mm and PLA user-confirmed.

The physical no-collision result is user-reported, not inferred from M23 ACK.
It clears the previously unobserved startup for this specific trial, not all
model placements, firmware semantics or prior-impact root cause. End behavior,
completion and print quality are not yet reported. No new agent hardware action
or general safety authorization. See ORCA_FINDER_DRAFT_02.md for exact scope.

## CLIENT-M28-015 — User-run cube save refused on reply spacing

User-host web slice capture
`web-data/proxy-test/captures/20261114T193405Z-9c2a6479c0fb` successfully
produced a 76579-byte Orca2.5 cube artifact. The following Save capture
`20261114T193412Z-d35656992ee7`, session s0001, reports the known Finder V1.5
fingerprint and READY. Its M28 response confirms the requested path/size but
uses **three ASCII spaces** before `Length:`, rather than the two in earlier
observations. Client rejected that formatting before sending any binary frame.
Only M601/M115/M119/M28 were sent; no M29, M23, M26 or cleanup was injected
into the pending binary phase. Partial/temporary printer state is unknown;
no agent retry or hardware action was performed.

The client now accepts exactly the observed two/three-space separators while
still matching the entire destination and decimal size exactly. Filename
spaces are not collapsed/split; tab, wrong path/size, extra body lines and other
separator widths remain rejected. Independent generated loopback tests cover
fragmented three-space replies, internal filename spaces and refusal without
payload on mismatches. Raw captures remain unchanged/private. Framing, CRC,
ACKs, timeouts and final-save rules are unchanged; this does not generalize
firmware error/retry behavior. The paused plugin transport is unchanged.

## GX-PREVIEW-014 — Embedded bitmap decoded offline

The supplied working `test1.gx` contains a standalone14454-byte BMP at byte58,
ending exactly at the declared G-code offset14512. Actual BMP fields establish
80×60 pixels,24-bit BI_RGB (uncompressed), BGR triplets, bottom-up rows and a
240-byte stride. Verbatim extraction was viewed locally and depicts the supplied
holder. No original image/model is committed. See [GX_PREVIEW.md](GX_PREVIEW.md)
for full byte layout and `tools/extract_gx_preview.py` for bounded read-only
extraction. This is one file's container observation, not firmware compatibility
or complete header semantics; no GX generator or hardware trial is introduced.

## FP-M650-001 — User-reported FlashPrint connection attempt

- **Evidence:** user-provided mock log, dated `2026-11-12 14:29:22` (timezone unknown). No raw capture, FlashPrint version, OS or real-printer firmware was supplied.
- **Observed incoming sequence:** `~M601 S1` → `~M115` → `~M650` → about one second later `~M602`, followed by disconnect. The old mock logged `M650` as unsupported and its implementation sends an error for that command.
- **Interpretation:** the rejection is a plausible reason FlashPrint abandoned the connection, but the log alone does not prove it is the only issue or that the identity response was fully accepted.
- **External evidence:** [S6] describes `M650` as reading machine extruder distance and shows `X: 25 Y: 15` followed by `ok`. [S3] describes XY offsets on 5M-series machines. Neither establishes Finder 2's exact response.
- **Synthetic hypothesis:** return `CMD M650 Received.\r\nX: 0 Y: 0\r\nok\r\n`, using the mock's existing reply envelope. Zero values, the envelope and allowing reads without control are mock conventions, not observed Finder behavior. No offset setter or movement is implemented.
- **Regression:** `test_reported_connection_sequence_with_m650` checks the reported command order against the mock; `test_m650_is_read_only_and_rejects_arguments` checks repeatable replies and unchanged control ownership/storage.
- **Next validation:** restart the updated mock and retry FlashPrint. Record the next commands/UI outcome and FlashPrint version. A real-printer reply capture is still needed to validate formatting and values.

## FP-IDENTITY-002 — Second identity query followed by disconnect

- **Evidence:** subsequent user-provided mock log dated `2026-11-12 14:34:08` (timezone unknown). Client version, OS, selected machine profile and UI error remain unknown.
- **Observed sequence:** `~M601 S1` → `~M115` → `~M650` → `~M115` → `~M602` → disconnect, all within milliseconds. No unsupported-command warning appears.
- **Conclusion:** adding `M650` changed the client's observed progression, but did not produce a sustained connection. The log alone cannot establish why FlashPrint released control or whether any particular reply was accepted.
- **Hypotheses:** model/identity recognition, firmware string parsing, required identity fields or offset reply formatting. Do not silently change identity fields based on this log alone.
- **Next experiment:** record both this mock attempt and a successful real-printer connection with the same client/profile through the new [recording proxy](PROXY.md), then compare exact request/reply bytes. Persistent [captures](CAPTURES.md) now make replies and historical sessions available without copying terminal logs. Hardware experiments remain manual and explicitly approved.
- **Local validation:** `test_reported_second_m115_sequence_has_full_reply_history` checks recording of two sessions using the reported command order; it is not a FlashPrint acceptance test.

## Evidensnivåer

- **Kodobservation:** vad projektets befintliga program gör; bevisar inte skrivarens beteende.
- **Extern uppgift:** vad en länkad källa uppger för angiven modell/familj.
- **Hypotes:** något vi avser att testa.
- **Locally observed/reference-backed:** a recorded attempt with environment and capture references. FINDER-IDLE-003 and FINDER-MOCK-004 now provide bounded evidence; missing environment details remain explicit.

## Initial hypothesis inventory (predates the captured baseline)

The following inventory records the starting assumptions. See the observations above for newer evidence; do not treat these initial unknowns as a summary of current implementation.

| Ämne | Vad vi har | Status och nästa kontroll |
| --- | --- | --- |
| Transport | `upload.py` och Finder-repo [S1] använder TCP 8899. | Rimlig standard; verifiera på användarens Finder 2. Gör porten konfigurerbar i nya verktyg. |
| Kommandon | Skriptet skickar ASCII med `~` och `\r\n`. [S1, S3] beskriver samma form. | Mät exakta byte, inklusive radslut och eventuella varianter. |
| Kontrollsession | Skriptet använder `~M601 S1` och `~M602`. [S1] beskriver kontrollbegäran. | Mät krav, svar, ägarskap och beteende efter avbrott. |
| Svarsavslut | Skriptet kräver en separat rad `ok`. [S3] visar också andra former av bekräftelse. | En generell `ok`-detektor är inte verifierad. Ta reda på avslut per kommando. |
| Upload | Skriptet skickar `~M28 <storlek> 0:/user/<namn>`, råa byte, paus, `~M29`. | Oprövad Finder 2-hypotes. Råström beskrivs för A3/A4 Pro [S3], inte därmed Finder 2. |
| CRC/block | [S1] rapporterar CRC-problem vid upload. | Ledtråd, inte bevis för viss CRC-algoritm eller paketlayout. Jämför fungerande FlashPrint-flöde. |
| Tidsberoende | Skriptet har tre sekunders paus före M29. | Ingen lokal evidens för att pausen behövs eller räcker. |
| Filformat | Skriptet visar `.gx` som exempel men granskar inte innehållet. | Bekräfta format från FlashPrint och vad Finder 2 accepterar. |
| UDP discovery | Externa källor beskriver flera olika varianter. | Ingen variant verifierad för denna Finder 2; se nedan. |

## Portar: TCP är inte UDP

`8899/TCP` är den starkaste utgångspunkten för kommandokanalen. Även om firmware använder en fast port bör våra verktyg tillåta annan lyssningsport, målport och lokal bindningsadress för tester och portkonflikter. FlashPrint kan däremot kräva en bestämd port eller följa en port annonserad i discovery; det måste mätas.

Discovery-källorna ska hållas isär:

- I Cura-ärendet [S5] finns en **Adventurer 3**-observation med multicast `225.0.0.9:19000/UDP`, lokal port `18001` och en probe vars payload rapporteras innehålla avsändar-IP och svarsport. Ärendets titel gäller Finder men detta enskilda exempel gäller inte Finder 2.
- Wikins legacy-beskrivning [S4] gäller **Adventurer 3/4 Pro** och anger multicast `225.0.0.9:8899/UDP`, med ett 140-byte-svar.
- Samma wiki anger `19000/UDP` och broadcast `48899/UDP` för nyare modeller. Det är inte evidens för att Finder 2 använder dessa.

Skillnaderna kan bero på firmware, klientversion eller olika discovery-vägar. Vi ska fånga FlashPrints sökning och riktiga skrivarens svar innan vi väljer paketmall. Börja med bred UDP-fångst så att en felaktig portgissning inte döljer trafiken. Simulator/proxy måste annonsera sin nåbara adress/port, inte råka skicka tillbaka den riktiga skrivarens identitet och dirigera FlashPrint förbi inspelningen.

## Befintligt skript: kända begränsningar

`upload.py` är användbart som läsbar hypotes men ännu inte en robust protokollklient:

- Port 8899 är hårdkodad; ingen capture, simulator eller upptäckt av skrivare.
- Varje `read_reply` har en egen buffert och lämnar inte tillbaka eventuella efterföljande meddelanden till nästa läsning.
- Sökning efter en `ok`-rad sker på delvis mottagen text. Den kan både missa andra giltiga svar och tolka en ofullständig rad som klar.
- Ett svar som innehåller både fel och `ok` hanteras inte med verifierad felprioritet.
- Timeout kan ge partiellt svar; `command()` kontrollerar sedan bara förekomsten av `ok`.
- Blockstorlek 4096 är en lokal `read`/`sendall`-detalj, inte bevis på skrivarens protokollblock.
- Fast paus före M29 och upload med råa byte saknar lokal verifiering.
- Skriptet skickar inget explicit utskriftsstartkommando, men upload-only-beteendet måste ändå verifieras på aktuell firmware.

## WEB-STATUS-018 — Active monitoring orchestration, dummy only

The web backend now maintains a firmware-gated M601/M115 status session with
serial M119/M105/M27 batches, waiting one second after each batch. Default
startup connection is selected by the proxy/owned-dummy launcher at the user's
request, not by browser GETs. This is implementation policy, **not a newly
measured firmware timing requirement or spontaneous-event subscription**.
The query/release shapes remain those previously observed on Finder V1.5;
FlashPrint version remains unknown. No CRC/framing/parser termination or
motion semantics were inferred/changed. Shared-lock tests use fresh ephemeral
loopback dummies to verify connection release before exact Save, later status
resumption, no automatic M23/M26 and no monitor reconnect after uncertain I/O.
These are local orchestration checks, not independent hardware compatibility
or proof of physical progress/completion. No agent printer/proxy connection
was made. See STATUS.md / CAPTURES.md for recording/quota/freshness details.
Physical persistent-session acceptance and browser rendering remain pending.

## WEB-WORKBENCH-001 — Standalone HTTP workflow, dummy only

Local application evidence, not a new physical-printer protocol observation:
HTTP file receipt followed by a separate confirmed Save transferred the supplied
3668165-byte GX to a freshly started ephemeral `finder-v1.5` dummy, exact bytes,
896 frames, no virtual print. Private capture
`web-data/manual-gx/captures/20261114T132526Z-4112e567c689`, session `s0001`.
Commands were M601/M115/M119/M28/M29/M602 only. FlashPrint was not involved;
its version is not applicable. The dummy reports the existing Finder V1.5
fingerprint; host Python is 3.11 on Debian 12. Self-consistent client/dummy
success does not extend firmware/hardware evidence.

A separate offline HTTP Slice with native Orca 2.3.0 and the unchanged private
Finder draft reached the known Sailfish validation failure with a generated
binary review cube. Capture
`web-data/native-profile-check/captures/20261114T132526Z-fe43872dc961` has no
printer sessions or generated output. The page reports the failure instead of
substituting a flavor or attempting a save. See [WEB.md](WEB.md) for trial
limits, the initial mesh-loading failure and reproducible fake/native setup.
No physical printer/proxy was contacted and no additional commands were inferred.

## Frågor som fångster ska besvara

1. Öppnar FlashPrint en eller flera TCP-anslutningar? Krävs kontroll innan identifiering/status?
2. Vilka kommandon krävs för att klienten ska godkänna Finder 2:s identitet och visa redo?
3. Exakta svar, radslut, bekräftelser och ordning? Kommer data efter en initial `ok`?
4. Är upload råa filbyte eller block med header, sekvensnummer, längd och checksumma?
5. Avser deklarerad längd hela `.gx`-filen, payload eller något annat? Vad händer med sista blocket?
6. Finns ACK per block, återförsök eller separat dataanslutning?
7. Hur avslutas och verifieras överföringen? Vad betyder kvittot egentligen: mottaget, sparat eller bara syntaktiskt accepterat?
8. Vilka filnamn, sökvägar, ändelser och storleksgränser fungerar?
9. Skickar FlashPrint alltid utskriftsstart efter upload, eller finns ett separat upload-only-flöde?
10. Vad händer vid avbrott och nästa anslutning? Finns temporära filer eller kvarhållen kontroll?

## Mall för en ny observation

```text
ID:
Påstående / hypotes:
Evidensnivå:
Modell och firmware:
FlashPrint-version och operativsystem:
Capture-ID, session, riktning och byteoffset:
Försök / enda ändrade variabel:
Förväntat resultat:
Observerat resultat:
Alternativa förklaringar:
Hur försöket upprepas:
Säkerhetsbedömning och godkännande vid hårdvara:
```

## Källor och läsanvisning

Källorna granskades när grunddokumenten skrevs. De är sekundärmaterial tills uppgifterna reproducerats på användarens enhet. För framtida kodanvändning: kontrollera licens och spara commit/version; länkar till föränderliga README/wiki-sidor är inte frysta referenser.

- **[S1]** [vtolvr/flashforge-finder-api-enhanced](https://github.com/vtolvr/flashforge-finder-api-enhanced). README anger TCP 8899, kontrollsekvens och kända CRC-fel vid upload. Inte verifierat att detta är projektet användaren avser eller exakt samma Finder-variant.
- **[S2]** [01F0/flashforge-finder-api](https://github.com/01F0/flashforge-finder-api). Ursprung som [S1] hänvisar till; en kandidat för fortsatt kodgranskning, inte separat granskad här.
- **[S3]** [Parallel-7 TCP Protocol](https://github.com/Parallel-7/flashforge-api-docs/wiki/TCP-Protocol), läst via [spegel](https://github-wiki-see.page/m/Parallel-7/flashforge-api-docs/wiki/TCP-Protocol). Blandar skrivarfamiljer; upload-avsnittet gäller A3/A4 Pro.
- **[S4]** [Parallel-7 Discovery Protocol](https://github.com/Parallel-7/flashforge-api-docs/wiki/Discovery-Protocol), läst via [spegel](https://github-wiki-see.page/m/Parallel-7/flashforge-api-docs/wiki/Discovery-Protocol). Använd som hypoteskälla, inte Finder 2-specifikation.
- **[S5]** [Ultimaker/Cura #7829: FlashForge Finder support](https://github.com/Ultimaker/Cura/issues/7829). Lång diskussion med flera modeller; discovery-exemplet ovan uppger Adventurer 3.
- **[S6]** [Mrnt/OctoPrint-FlashForge G-Code Reference](https://github.com/Mrnt/OctoPrint-FlashForge/wiki/G-Code-Reference), read via [mirror](https://github-wiki-see.page/m/Mrnt/OctoPrint-FlashForge/wiki/G-Code-Reference). Its `M650` section reports machine extruder distance and an XY-shaped reply; it does not verify this project's Finder 2 response. Treat as a response-shape hypothesis, not a firmware specification.
