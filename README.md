# FlashForge Finder 2 protocol lab

Reverse-engineer the Finder 2 network protocol, build a realistic offline simulator, and provide a standalone local drag-and-drop upload workbench with optional offline Orca slicing. **Uploading must not automatically start a print.**

## Current status

Implemented:

- An **offline TCP printer mock**, using Python 3.11+ and the standard library only. Its default `finder-v1.5` profile supports captured-style idle replies and framed upload, plus explicit virtual start/cancel. Earlier profiles remain selectable.
- Identity/status replies, control ownership, bounded RAM-only virtual upload storage and a mock file listing.
- **Persistent traffic logs and connection history** for mock, proxy and client commands, with exact request/reply streams.
- A **recording TCP proxy** for comparing FlashPrint traffic with the real printer's responses.
- A **print-file upload CLI and reusable async client** for `.gx`, `.gcode` and `.g`, with exact block ACKs/CRC32, upload-only defaults, explicit upload `--start`, and separate confirmed start/stop actions.
- An **optional Orca CLI adapter**: offline `slice MODEL.stl`, or `upload MODEL.stl --slice` before any printer connection, using explicit trusted JSON profiles and bounded child processes. Native Orca/profile compatibility still needs a host trial.
- Automated localhost tests, including the existing uploader, recording failures, proxy transport and fake-slicer orchestration.
- A **standalone local page**: `python3 -m finderlab web`, with drag-and-drop, explicit offline slicing/review and a separate confirmed upload-only action. No accounts or OctoPrint setup. Orca/profile compatibility remains a blocker for native Finder slicing; existing FlashPrint GX files work independently.
- The original experimental [`upload.py`](upload.py), unchanged.

Not implemented in the research CLI: UDP discovery, replay/standalone analysis tooling, or physical job dynamics. The experimental OctoPrint plugin at `plugins/octoprint-flashforge-finder2` is **paused**, not a native Finder printer driver. The standalone page is now the primary UI; browser/container acceptance remains pending. **FlashPrint connection, upload and explicit virtual start/stop have now been observed against the dummy.** The new client has also uploaded the user's 3.67 MB GX to a fresh dummy with an exact byte match and no job started. A subsequent user-run host/proxy trial confirmed the new client's real-printer upload-only flow: all blocks, final save and release acknowledged, no start/stop sent. Other firmware, errors/retries and physical job-control actions remain separately bounded; mock success alone is not hardware evidence.

## Open the standalone page (dummy first)

In terminal 1, start a fresh dummy:

```sh
python3 -m finderlab mock --port 9000
```

In terminal 2:

```sh
python3 -m finderlab web --enable-upload --target-port 9000
```

Open **http://127.0.0.1:8000**. Drop an existing FlashPrint `.gx` (or `.gcode`/`.g`), then explicitly confirm **Save to Finder · no start**. Selecting a file does not connect to a printer. STL requires separately configured Orca and trusted profiles. The old Sailfish draft is still rejected; a separately authorized **offline Marlin-emission draft 02 now slices natively**, but is not a print-ready or physically validated Finder profile. Generated-output saving is blocked by default pending separate profile review. Uploads are disabled without `--enable-upload`. To deliberately enable separate **Start saved file** and **Request cancel** buttons, also add `--enable-job-controls`. Each requires its own confirmation; Start may heat/move, and Cancel is not an emergency stop. Saving still never starts a print.

See **[docs/WEB.md](docs/WEB.md)** for the workflow, native Orca configuration, private storage, limits and Podman commands. The default Compose now starts this standalone page, not OctoPrint. No printer is discovered and a loopback proxy can still reach real hardware.

## Upload a print file with the CLI (dummy first)

Terminal 1:

```sh
python3 -m finderlab mock
```

Terminal 2:

```sh
python3 -m finderlab upload upload/test1.gx
```

The client defaults to `127.0.0.1:8899`. Confirm this is the **dummy**, not a proxy to hardware. It preserves the source bytes/extension (including GX thumbnails or plain G-code), validates block ACKs and final save, and sends **no start or stop by default**. Use `--port` for a different endpoint and `--remote-name "client sample.gx"` for an ASCII destination basename. Only observed Finder firmware `V1.5 20170419` is enabled.

To explicitly start after confirmed save, add `--start`:

```sh
python3 -m finderlab upload "upload/example.gcode" --start
```

Test against the dummy first. This flag may heat/move a real printer or a printer behind a proxy. It starts only after successful save and READY validation, never after a failed/uncertain upload, and never appends an automatic stop. Format support is **not** conversion, G-code safety validation or proof of physical firmware support for every extension.

Read [docs/CLIENT.md](docs/CLIENT.md) for proxy/direct hardware trials, safety confirmations, status/start/stop commands, errors and persistent client logs. A hardware trial requires physical supervision and explicit approval; non-loopback targets also require `--allow-hardware`. Orca slicing integration is optional and requires separately installed Orca plus explicit profiles; verified Finder-profile and GX/thumbnail generation remain deferred—use a known-working FlashPrint file for initial hardware trials. The old `upload.py` remains unchanged and is not the new client.

## Slice STL with Orca (offline first)

Download a pinned official Linux x86_64 AppImage with `python3 tools/download_orca.py` (older glibc selects 2.3.0; otherwise 2.5.0). It verifies size/SHA-256 but does not execute/extract the application or install runtime packages. See [docs/ORCA_INSTALL.md](docs/ORCA_INSTALL.md) for setup. Then supply self-contained machine/process/filament JSON profiles:

```sh
python3 -m finderlab slice upload/model.stl \
  --orca /path/to/orca-slicer \
  --machine local-profiles/finder-machine.json \
  --process local-profiles/finder-process.json \
  --filament local-profiles/pla.json \
  --output upload/model-review.gcode
```

For a combined workflow, use `upload upload/model.stl --slice` with those same profile/executable options and your dummy's `--port`. Slicer failure prevents all printer connections; printing is still opt-in. No reviewed Finder 2 Orca profile ships yet. Native Orca 2.3.0 help/capability probing succeeds after approved runtime installation. A copied/edited local Finder draft now passes structural checks but native slicing is blocked by rejected Sailfish flavor; see [docs/ORCA_FINDER_DRAFT_01.md](docs/ORCA_FINDER_DRAFT_01.md). A separate user-approved [draft 02](docs/ORCA_FINDER_DRAFT_02.md) now slices a generated cube and the supplied holder natively with 2.3.0, including an explicit slow Z layer-change step after detecting mixed-XYZ overspeed. These are offline review artifacts, **not approved for printing**; original profiles remain unchanged. Physical/motion/profile validation is still outstanding; automated orchestration tests continue using a fake CLI. See [docs/ORCA_INSTALL.md](docs/ORCA_INSTALL.md) for host installation, the probe reference and the newer 2.5.0 build's ABI blocker. See [docs/SLICING.md](docs/SLICING.md) for profile/inheritance requirements, logs, resource limits and remaining host validation. The standalone page exposes the same optional adapter with separate slice/review/save steps; GX/thumbnail creation and a validated Finder profile are not implemented.

## Offline G-code diagnostics (not safety approval)

```sh
python3 -m finderlab review path/to/file.gcode
# For a reference file without explicit M82/M83, label the intended-E assumption:
python3 -m finderlab review path/to/reference.gx --assume-absolute-e
```

Reads only: reports declared coordinates, E deltas, nominal resolved Z components, unmodeled homing and warnings. It diagnoses the old copied +363 mm E-only end step, but **does not certify collision safety or firmware compatibility**. See [docs/ORCA_FINDER_DRAFT_02.md](docs/ORCA_FINDER_DRAFT_02.md) for native output findings and the private, read-only web slicing setup. Use a new output file for review reports; never overwrite your source.

## Paused OctoPrint experiment

A separate GPLv3 repository is included as `plugins/octoprint-flashforge-finder2`. See its README and [docs/OCTOPRINT.md](docs/OCTOPRINT.md) for scope, safety limits and a local dummy test. Initialize the submodule before building:

```sh
git submodule update --init --recursive
# Start a fresh local dummy separately:
python3 -m finderlab mock --port 9000
docker compose -f compose.octoprint.yml config
docker compose -f compose.octoprint.yml up --build
```

This is the preserved old experiment, **not the recommended standalone workflow**. Its Compose setup shares the host network so OctoPrint can reach a host-loopback dummy/proxy. OctoPrint binds to `127.0.0.1:5000`; no serial device or Docker socket is passed through. On first run, finish OctoPrint setup, then configure plugin target `127.0.0.1:9000` and explicitly enable uploads. The plugin defaults disabled. **Do not point it at a hardware proxy unless you intend a real upload.** Loopback is not a safety guarantee. Docker/Compose runtime and browser testing remain pending; this example currently targets Linux host networking.

## Run the dummy printer

From the project directory, no installation required:

```sh
python3 -m finderlab mock --verbose
```

It listens on **127.0.0.1:8899** by default. Connect FlashPrint manually to that address. The mock saves only after `M29`, starts a virtual job only after `M23`, and cancels only after an explicit `M26`. It never heats, moves, executes G-code or connects to hardware.

The original `upload.py` uses raw bytes and **does not implement the observed block/CRC/ACK protocol**. To test that old script locally, explicitly run the legacy profile instead of the default:

```sh
python3 -m finderlab mock --profile synthetic-v1
# In another terminal:
python3 upload.py 127.0.0.1 path/to/model.gx
```

That legacy test does not validate a model or prove hardware compatibility. Virtual files disappear when the mock exits, but **recorded payload bytes persist on disk**. Every run prints its capture directory under `captures/`: start with `traffic.log` for timestamped requests/replies and connection history. Raw streams preserve bytes beyond the log's bounded previews. Recording is enabled even without `--verbose`; Ctrl+C finalizes the manifest.

Logs in this workspace can be inspected directly by the assistant when you provide their path. Logs on another computer must be copied here deliberately. See [docs/CAPTURES.md](docs/CAPTURES.md) for privacy and storage limits.

For a different local port:

```sh
python3 -m finderlab mock --port 9000
```

The old uploader still has a hardcoded port of 8899. Use a TCP test client for other ports. See [docs/MOCK.md](docs/MOCK.md) for commands, limits, troubleshooting and manual FlashPrint testing.

## Record actual printer responses

For an approved, supervised hardware experiment, stop the mock and replace the documentation IP below with the printer's actual address:

```sh
python3 -m finderlab proxy --target-host 192.0.2.10 --target-port 8899
```

Connect FlashPrint manually to **127.0.0.1** on the proxy computer. Begin with connection/status only. The proxy forwards **all** commands unchanged, including print-start and heating; it is not a safety filter. No discovery is implemented. See [docs/PROXY.md](docs/PROXY.md) for a local-only trial, network configuration and diagnosis of the current disconnect.

## Run tests

```sh
python3 -m unittest discover -s tests -v
# Optional Node.js 18+ UI-logic checks (no npm dependencies):
node tests/test_web_ui.js
```

Tests use ephemeral loopback ports and never connect to a physical printer. Generated test files use the ignored project-local `.tmp/` directory and are cleaned up; do not use the system temporary directory for project work. No third-party dependencies are required. One integration test retains the uploader's existing three-second pause.

## Components and next steps

| Component | Purpose |
| --- | --- |
| Recording proxy (implemented; localhost-tested) | FlashPrint → proxy → explicit target, preserving both byte streams. |
| Evidence-based simulator | Reproduce observed Finder 2 identity, sessions, status, transfer and discovery. |
| Analysis and replay | Inspect captures, compare experiments and generate regression fixtures. |
| Upload client and web UI | CLI plus standalone loopback workbench implemented; OctoPrint experiment paused. Native Finder slicer-profile and live browser/container acceptance remain outstanding. |

A real-printer connection/status capture now supplies independent regression fixtures, with private identity fields anonymized. The user's subsequent mock recording confirms sustained FlashPrint idle polling. A second capture now establishes the observed upload framing and start/cancel reply formats. Dynamic job behavior, error/retry handling and discovery still need evidence. Small regression fixtures are retained; a broader systematic log corpus/replay system is future work.

## Documentation

New documentation is English; older Swedish sections will be translated incrementally.

- [DESIGN.md](DESIGN.md): architecture, realism goals and safety boundaries.
- [docs/WEB.md](docs/WEB.md): standalone page, Podman, optional Orca configuration and current profile blocker.
- [docs/OCTOPRINT.md](docs/OCTOPRINT.md): paused plugin experiment and preserved container test.
- [docs/traces/](docs/traces/README.md): reviewed sanitized, non-replayable trace derivatives.
- [AGENTS.md](AGENTS.md): contributor/agent rules, including milestone commits.
- [docs/CLIENT.md](docs/CLIENT.md): upload program, manual printer trials and separate job controls.
- [docs/MOCK.md](docs/MOCK.md): implemented mock behavior and usage.
- [docs/PROXY.md](docs/PROXY.md): recording proxy and real-response comparison.
- [docs/PROTOCOL.md](docs/PROTOCOL.md): evidence, hypotheses and open protocol questions.
- [docs/CAPTURES.md](docs/CAPTURES.md): implemented logs, history, recording format and privacy.
- [docs/EXPERIMENTS.md](docs/EXPERIMENTS.md): reverse-engineering procedures.
- [docs/ROADMAP.md](docs/ROADMAP.md): milestones and acceptance criteria.
- [docs/ORCA_INSTALL.md](docs/ORCA_INSTALL.md): local AppImage versions, runtime blockers, integrity provenance and host setup.
- [docs/SLICING.md](docs/SLICING.md): implemented Orca CLI adapter, offline/combined workflows, trusted profile requirements and native-validation limitations.
- [docs/FLASHFORGE_PROFILE_REVIEW.md](docs/FLASHFORGE_PROFILE_REVIEW.md): inspection of the user's official Orca ZIP and Finder material settings in FlashPrint; not a print-ready Orca profile.
- [docs/ORCA_FINDER_DRAFT_02.md](docs/ORCA_FINDER_DRAFT_02.md): native offline Marlin-emission experiment, extrusion/coordinate/Z diagnostics and unresolved physical blockers; not print approved.
- [docs/ORCA_FINDER_DRAFT_01.md](docs/ORCA_FINDER_DRAFT_01.md): local copied/edited Finder comparison presets and the observed Sailfish validation blocker; not a print-ready profile.
- [docs/SLICING_ANALYSIS.md](docs/SLICING_ANALYSIS.md): offline analysis of supplied FlashPrint/Prusa samples, extrusion-state errors and remaining profile risks (not a print-ready replacement).
- [docs/PRUSA_ITERATION_01.md](docs/PRUSA_ITERATION_01.md): user-requested start/end candidates and settings for offline re-slicing/review only; not hardware-validated.
- [docs/QUESTIONS.md](docs/QUESTIONS.md): environment and product decisions still needed.

## Safety

The mock has no outgoing printer connection and never executes G-code. Bind to loopback by default; use an explicit host address only when deliberately exposing the mock on a trusted LAN. Do not expose any project service or the real printer to the internet.

Hardware experiments require explicit approval and physical supervision. The old uploader is incompatible with the observed framing. The new client's upload-only workflow is dummy-tested and now has one successful user-run physical-printer trial; other firmware, physical job controls and failure cases require their own verification. Uploading does not validate G-code safety or fix incompatible slicer output. The implemented transparent proxy forwards dangerous commands too; it is not a safety filter.
