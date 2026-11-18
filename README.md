# FlashForge Finder 2 protocol lab

Reverse-engineer the Finder 2 network protocol, build a realistic offline simulator, and provide a standalone local drag-and-drop upload workbench with optional offline Orca slicing. **File receipt/slicing must not start a print; explicit save/start intent is required.**

## Current status

Implemented:

- An **offline TCP printer mock**, using Python 3.11+ and the standard library only. Its default `finder-v1.5` profile supports captured-style idle replies and framed upload, plus explicit virtual start/cancel. Earlier profiles remain selectable.
- Identity/status replies, control ownership, bounded RAM-only virtual upload storage and a mock file listing.
- **Persistent traffic logs and connection history** for mock, proxy and client commands, with exact request/reply streams.
- A **recording TCP proxy** for comparing FlashPrint traffic with the real printer's responses.
- A **print-file upload CLI and reusable async client** for `.gx`, `.gcode` and `.g`, with exact block ACKs/CRC32, upload-only defaults, explicit upload `--start`, and separate confirmed start/stop actions.
- An **optional Orca CLI adapter**: offline `slice MODEL.stl`, or `upload MODEL.stl --slice` before any printer connection, using explicit trusted JSON profiles and bounded child processes. Native2.3 and user-host2.5 slicing evidence is scoped in the profile docs; container acceptance remains pending.
- Automated localhost tests, including the existing uploader, recording failures, proxy transport and fake-slicer orchestration.
- A **standalone local page**: `python3 -m finderlab web`, with drag-and-drop, explicit offline slicing/review and explicit save-only or combined save/start intent. No accounts or OctoPrint setup. The tracked skirt03 profile now slices offline with native Orca; broader physical/container compatibility remains scoped, not a universal guarantee. Existing FlashPrint GX files work independently.
- The original experimental [`upload.py`](upload.py), unchanged.

Not implemented in the research CLI: UDP discovery, replay/standalone analysis tooling, or physical job dynamics. The experimental OctoPrint plugin at `plugins/octoprint-flashforge-finder2` is **paused**, not a native Finder printer driver. The standalone page is now the primary UI; browser/container acceptance remains pending. **FlashPrint connection, upload and explicit virtual start/stop have now been observed against the dummy.** The new client has also uploaded the user's 3.67 MB GX to a fresh dummy with an exact byte match and no job started. A subsequent user-run host/proxy trial confirmed the new client's real-printer upload-only flow: all blocks, final save and release acknowledged, no start/stop sent. Other firmware, errors/retries and physical job-control actions remain separately bounded; mock success alone is not hardware evidence.

## Run the real Finder workflow with Compose

Linux x86_64, including Orca/Finder2 profiles and the recording proxy:

```sh
# In your clone (back up an existing .env before replacing it):
cp .env.example.live .env
# Set FINDER_PRINTER_HOST in .env to the verified printer IP.
# For LAN access, also set FINDER_LISTEN_HOST to this SERVER's192.168 IP.
podman compose up --build -d
podman compose logs finder-web
```

`docker compose` also works. The live example selects/starts the proxy and waits
for passive listener readiness before web/status startup; no separate proxy
command or profile flag. Save, generated output, Start/Cancel and monitoring are
enabled; **Save + start defaults checked**, uncheck for save only. Startup status
queries do not start/cancel printing. Close other control clients first. Missing
printer IP fails rather than guessing or falling back to dummy. No Internet
exposure; trusted-LAN HTTP is unencrypted. Full setup/troubleshooting and remaining
host/provider acceptance: [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).

With your working private `.env` in place, the short server launcher is:

```sh
./tools/start_server.sh
```

It runs `podman compose up --build -d` from the project directory. It refuses a
missing `.env` rather than selecting a dummy or guessing network settings. Run
only when no upload/Slice/start operation is active.

## Package source for an upgrade

On GitHub: **Actions → Source release → Run workflow** creates downloadable ZIP /
tar.gz sources and checksums without running the tests or requiring tools on your
host. It needs the workflow pushed to the default branch first; no automatic
GitHub Release/deployment. See [docs/RELEASES.md](docs/RELEASES.md).

```sh
./tools/package_release.sh                  # Fast archive only; tests NOT RUN
./tools/package_release.sh --check --jobs 4 # Alternative: full checks, then archive
```

Exports reviewed, committed HEAD to `dist/releases/finderlab-COMMIT/` with SHA256
and metadata explicitly saying whether tests ran. Requires clean tracked files;
private `.env`, passwords, models and captures are excluded. Ordinary packaging
needs no Node/container tools and never starts services. The Bash wrapper saves
complete output/errors to a unique private `.tmp/package-logs/*.log`, prints its
path and preserves failures. Same-commit output is
not overwritten. Preserve your private `.env`, Compose project name and volumes
when upgrading, and wait until no job is active. See [docs/RELEASES.md](docs/RELEASES.md).

## Clone and run a simulator rehearsal with Docker Compose

Linux x86_64 server/local machine, including Orca and the Finder2 profiles;
**owned-dummy mode below is only a rehearsal, not your physical printer**:

```sh
git clone https://github.com/mls-m5/flashforge-api.git
cd flashforge-api
cp .env.example .env
docker compose up --build -d
docker compose logs -f finder-web
```

Open `http://127.0.0.1:8000` on that server. For trusted-LAN access, set the
server's specific192.168 address in `.env`; the initial login is printed once
in logs, then persists as a salted hash and can be changed in the GUI. No wildcard/public binding or automatic hardware connection. For the
**STL→Slice→GX→virtual Save** workflow, Orca and the existing skirt03 configuration
are now included by default: **no manual profile copying**. The reviewed source
JSONs, upstream attribution and license are tracked in `profiles/finder2/`.
An opt-in
`printer` Compose profile can run the recording proxy to an explicitly verified
IP. Full setup, environment examples and persistence/backup instructions:
**[docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)**. Docker/Podman runtime/build acceptance
remains host-run; neither runtime is available in the agent environment.

## Open the standalone page (dummy first)

In terminal 1, start a fresh dummy:

```sh
python3 -m finderlab mock --port 9000
```

In terminal 2:

```sh
python3 -m finderlab web --enable-upload --target-port 9000
```

Open **http://127.0.0.1:8000**. Drop an existing FlashPrint `.gx` (or `.gcode`/`.g`), then click **Save to Finder · no start**. Selecting a file does not connect to a printer. STL requires separately configured Orca and trusted profiles. The old Sailfish draft is still rejected; a separately authorized **offline Marlin-emission draft 02 now slices natively**, but is not a print-ready or physically validated Finder profile. Generated-output saving is blocked by default pending separate profile review. Uploads are disabled without `--enable-upload`. To deliberately enable separate **Start saved file** and **Request cancel** buttons, also add `--enable-job-controls`. Each requires its own button click (no popup); Start may heat/move, and Cancel is not an emergency stop. With job controls enabled, the new **Start print when upload completes** checkbox is checked by default: the clearly labelled Save + start click composes confirmed save and one fresh-READY start. Uncheck for save only. No start on failed/unknown save, release or recording failure. See [docs/START_AFTER_UPLOAD.md](docs/START_AFTER_UPLOAD.md). CLI defaults remain upload-only.

For a one-command local slicing/upload test, stop any previous web server and run `./tools/start_dummy_upload_test.sh`. It owns a fresh ephemeral dummy (not an existing hardware proxy), enables virtual Save and separately confirmed virtual Start/Cancel (no G-code execution). No separate dummy process is needed. This requires a local Orca installation; the Finder2 profiles are tracked in
`profiles/finder2/`. It does not authorize physical printing.

For a simple **virtual** light/XYZ/extruder panel without Orca or profiles, run
`./tools/start_control_panel_test.sh`. It owns a fresh dummy; counters and its
warm-nozzle flag are toy state, not hardware feedback. Physical/proxy manual
controls remain locked pending verified small-step/thermal/mode behavior. See
[docs/MANUAL_CONTROLS.md](docs/MANUAL_CONTROLS.md).

**3MF models are now accepted** alongside STL: core meshes are imported as
geometry only, never project printer/filament/start-code settings. Unsupported
assemblies/extensions fail explicitly. Slice, Save and Start remain separate.
See [docs/3MF.md](docs/3MF.md) for limits and the supplied tool's offline trial.

The Slice section has **layer-height, brim and independent XY hole/contour controls**.
Layer/brim default to the server profile; hole compensation starts at0mm (off).
For holes about0.4mm too small in diameter, +0.2mm per edge is a calibration
trial, not a guaranteed fit. Clear the hole field to use the profile. Only a
new confirmed Slice changes: existing files, original profiles,
first-layer height and retraction are untouched. The separate contour control
also starts at0; −0.2mm shrinks outer dimensions by about0.4mm. Both are fixed
per-edge offsets, not scaling; inspect thin walls and calibrate. Applied values
are recorded per artifact. See [docs/HOLE_COMPENSATION.md](docs/HOLE_COMPENSATION.md).
Review brim/hole footprint and thin walls before printing.

See **[docs/WEB.md](docs/WEB.md)** for the workflow, native Orca configuration, private storage, limits and Podman commands. The default Compose now starts this standalone page, not OctoPrint. No printer is discovered and a loopback proxy can still reach real hardware.

For deliberate proxy use, `./tools/start_printer_proxy.sh CONFIRMED_PRINTER_IP`
starts a loopback recording relay, then `./tools/start_proxy_web.sh` enables
confirmed Save to it. The recalled IP `192.168.0.39` must be verified by the
operator; no discovery/probe occurs. Start/Cancel and generated-output saving
require separate flags; see [docs/WEB.md](docs/WEB.md). **The proxy web launcher
now starts status polling automatically** (about one second between batches).
Verify the proxy target and close FlashPrint/other clients first. Use
`--no-monitor` to leave polling off at startup. Stop status polling does not
cancel a print; the offline launcher and passive watcher remain disconnected. The proxy is not a safety
filter and the new candidate's physical startup remains unverified.

## Standard priming: native skirt, not the fixed line

At the user's explicit request, all standard web launchers (offline, owned dummy,
proxy and LAN) now use the tracked `profiles/finder2/` draft03 native-skirt profiles with mandatory
`--check-priming`. Skirt follows the first-layer footprint, including manual
placement and brim. The fixed02 prime is no longer selected by these launchers;
missing03 fails without falling back. Existing G-code/printer files are not
rewritten: restart the backend and **re-slice**. Upload/start permissions and
checkbox behavior are unchanged. Nominal guards remain; this default change is
not new physical/host2.5 validation. See [docs/PRIMING_REVIEW.md](docs/PRIMING_REVIEW.md).

## Several STL models on one plate

Select/drop multiple STL files, or add more after the first file **before Slice**.
The shared 3D plate lets you select a part in the list or by clicking its mesh,
then change its XY position, rotation and uniform scale independently. Remove
parts individually; Slice produces one combined layer-by-layer job, and GX's
miniature includes the whole plate. Camera dragging is still camera movement,
not a model-drag gizmo. Up to8 STL files/64MiB/200k combined triangles; nominal
bounds and conservative1mm XY bounding-box gaps apply. Existing single3MF/print
file workflows remain separate. Restart the backend and hard-reload browsers.
See [docs/PLATE.md](docs/PLATE.md) for limits, native offline/HTTP evidence and
pending browser/host2.5 acceptance. No printer was contacted during development.

## Inspect the model before slicing

After selecting STL/supported3MF, the input model now appears in a separate
3D mesh view **before Slice**. Orbit/zoom/pan the camera, inspect dimensions or
switch wireframe. Display centering/on-bed translation is visual only; it does
not edit the file or choose Orca's placement by itself. **Numeric controls now
add uniform scale, XYZ rotation and XY model movement**, with +90°/Center/Reset
buttons and automatic Z-on-bed. Editing enables manual placement; explicit
Slice bakes a private geometry derivative and disables Orca auto-arrange.
Original files stay unchanged. Discard/reselect to edit a completed slice;
face-to-bed picking and mouse gizmos remain future work. Multiple STL models
are now supported in the shared plate view above.
See [docs/MODEL_TRANSFORMS.md](docs/MODEL_TRANSFORMS.md) for coordinate/resource
limits and actual offline native2.3 placement trials. The user accepted the
initial mesh view; new editor/browser/host2.5 acceptance remains pending.
Restart backend/reload browsers. Standard launchers now use native skirt that follows the first-layer footprint;
custom startup/homing still needs review. Inspect G-code before Save/Start.

## Create GX with a 3D miniature

After a supported Slice, click **Create GX + 3D thumbnail · no upload/start**.
The local CPU renderer generates an80×60 grayscale mesh miniature and a real
experimental GX envelope; **G-code body bytes remain unchanged**. The page shows
the bitmap and selects `.gx` for Download/later explicit Save. Generation itself
never uploads/starts, and generated-output/server job gates still apply. Restart
backend/reload browsers. Physical Finder screen/header acceptance remains
unverified; source-mesh miniature does not simulate supports/brim or print safety.
See [docs/GX_GENERATION.md](docs/GX_GENERATION.md) for header evidence, metadata,
limits, standalone tool and actual offline native/HTTP trial.

## Inspect the current toolpath

After Slice or selecting a server-side print file, a local Three.js view now
shows linear toolpaths with camera orbit/zoom/pan, deposition-height slider and
optional travel lines. It never fetches printer storage or sends commands.
Warnings identify unmodeled homing/arcs/modes; this is not collision/firmware
validation or physical material simulation. Three.js is vendored locally with
its MIT license, no CDN. See [docs/PREVIEW.md](docs/PREVIEW.md).

Browser action popups have been removed at the user's request. **A button click
acts immediately**; Save and Start remain separate, with unchanged server guards
and no automatic retries. Start shows the exact saved basename; inspect it and
coordinate with other operators. Restart the backend and reload browsers for
new code/assets. Actual rendered-browser/GPU acceptance remains pending.

## Share the full page on a trusted home network

Run `./tools/start_lan_web.sh`—no IP argument needed. It selects this Linux
computer's local192.168 address and prints the link to share. The printer proxy
stays on localhost. Slice, Save, confirmed Start/Cancel and status use the
existing proxy/profile setup. The browser asks for user
`finder` and the initial password printed by the server. It now survives restarts
as a salted hash; set your own in the page's **LAN login password** form.
See [docs/PASSWORDS.md](docs/PASSWORDS.md) for storage and offline reset.
Only192.168 peers plus local IPv4 are allowed; an optional narrower CIDR can
be selected. All users share one printer/file slot. **HTTP is unencrypted**;
trusted network only, no router forwarding/public tunnels. Default/offline
launchers stay loopback, and physical manual controls remain locked. See
[docs/LAN.md](docs/LAN.md) before enabling. No agent LAN/hardware trial was run.

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

Read [docs/CLIENT.md](docs/CLIENT.md) for proxy/direct hardware trials, safety confirmations, status/start/stop commands, errors and persistent client logs. A hardware trial requires physical supervision and explicit approval; non-loopback targets also require `--allow-hardware`. Orca slicing integration is optional and requires separately installed Orca plus explicit profiles; verified Finder-profile and physical generated-GX acceptance remain outstanding—use a known-working FlashPrint file for initial hardware trials. The old `upload.py` remains unchanged and is not the new client.

## Slice STL with Orca (offline first)

Download a pinned official Linux x86_64 AppImage with `python3 tools/download_orca.py` (older glibc selects 2.3.0; otherwise 2.5.0). It verifies size/SHA-256 but does not execute/extract the application or install runtime packages. See [docs/ORCA_INSTALL.md](docs/ORCA_INSTALL.md) for setup. Then use the included self-contained Finder2 machine/process/filament JSON profiles:

```sh
python3 -m finderlab slice upload/model.stl \
  --orca /path/to/orca-slicer \
  --machine profiles/finder2/machine.json \
  --process profiles/finder2/process.json \
  --filament profiles/finder2/filament.json --check-priming \
  --output upload/model-review.gcode
```

For a combined workflow, use `upload upload/model.stl --slice` with those same profile/executable options and your dummy's `--port`. Slicer failure prevents all printer connections; printing is still opt-in. The current experimental native-skirt03 profiles now ship in `profiles/finder2/`
with their upstream license/provenance; they are not a universally physically
validated preset. Standard launchers select them with mandatory priming guard. Native Orca 2.3.0 help/capability probing succeeds after approved runtime installation. A copied/edited local Finder draft now passes structural checks but native slicing is blocked by rejected Sailfish flavor; see [docs/ORCA_FINDER_DRAFT_01.md](docs/ORCA_FINDER_DRAFT_01.md). A separate user-approved [draft 02](docs/ORCA_FINDER_DRAFT_02.md) now slices a generated cube and the supplied holder natively with 2.3.0, including an explicit slow Z layer-change step after detecting mixed-XYZ overspeed. These are offline review artifacts, **not approved for printing**; original profiles remain unchanged. Physical/motion/profile validation is still outstanding; automated orchestration tests continue using a fake CLI. See [docs/ORCA_INSTALL.md](docs/ORCA_INSTALL.md) for host installation, the probe reference and the newer 2.5.0 build's ABI blocker. See [docs/SLICING.md](docs/SLICING.md) for profile/inheritance requirements, logs, resource limits and remaining host validation. The standalone page exposes the same optional adapter with separate slice/review/save steps; a separate experimental GX/CPU-thumbnail export now follows a supported Slice (see docs/GX_GENERATION.md), but a validated Finder profile is not provided.

For offline review of placement-aware priming, `./tools/start_skirt_test.sh`
selects separate draft03 with a native skirt instead of the fixed purge line.
This changes startup paths; it is offline/owned-dummy only in the launcher and
not physical-print approval. It now enables `--check-priming`, rejecting
unsupported/overlapping/out-of-nominal-margin first-layer candidates before they
become artifacts. The user has now selected the same guarded03 profile for
ordinary/proxy/LAN startup as well. The isolated script only separates workspace
and restricts target mode; physical validation is not inferred. See [docs/PRIMING_REVIEW.md](docs/PRIMING_REVIEW.md) for
the exact tool/manual-placement comparisons and newly found edge failure; see
[docs/ORCA_FINDER_DRAFT_03.md](docs/ORCA_FINDER_DRAFT_03.md).

## Observe printer status without another printer connection

With FlashPrint already polling through the recording proxy at localhost9000:

```sh
./tools/watch_printer.sh
```

Open **http://127.0.0.1:8001** for observed temperatures, machine state and file
progress. This page only reads existing recordings; no printer requests or
job actions are enabled. Samples show age/staleness; file progress is not time
remaining or proof of completion. The usual proxy page also includes the panel
on its next restart. See [docs/STATUS.md](docs/STATUS.md).

## Offline G-code diagnostics (not safety approval)

```sh
python3 -m finderlab review path/to/file.gcode
# For a reference file without explicit M82/M83, label the intended-E assumption:
python3 -m finderlab review path/to/reference.gx --assume-absolute-e
```

Reads only: reports declared coordinates, E deltas, nominal resolved Z components, unmodeled homing and warnings. It diagnoses the old copied +363 mm E-only end step, but **does not certify collision safety or firmware compatibility**. See [docs/ORCA_FINDER_DRAFT_02.md](docs/ORCA_FINDER_DRAFT_02.md) for native output findings and the private, read-only web slicing setup. Use a new output file for review reports; never overwrite your source.

For read-only first-layer priming diagnostics (tagged linear Orca subset):
`python3 tools/check_priming.py path/to/file.gcode`. It reports nominal XY
intersections/gaps, not collision/firmware/material safety; never connects or
rewrites the file. See [docs/PRIMING_REVIEW.md](docs/PRIMING_REVIEW.md).

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

## Storage quota and a blocked Slice

The default256MiB active quota is disk-backed workspace storage, **not RAM**.
Old captures and future monitor/Slice budgets count. At the user's request,
complete inactive captures now archive automatically on demand, intact under the
same workspace's `archive/captures/`, outside the active budget; archive cap2GiB.
No deletion, active-log/model moves or automatic retry. Errors stay visible next
to Slice. Optional `--storage-limit-mib 512` (bounded128–2048) changes the active
limit; `--no-auto-archive` opts out. Restart backend/reload for the new policy;
the proxy need not restart. See [docs/STORAGE.md](docs/STORAGE.md) for protection,
index/retention limits and confirmed507 recovery. Deleting `.tmp/` is unrelated.

## Run tests

```sh
# Full checks: Python suite + all tests/test_*.js (Node.js 18+) + trace integrity:
./tools/check.sh
# Faster Python tests in four isolated processes (same checks, more CPU/RAM):
./tools/check.sh --jobs 4
# Equivalent without Bash:
python3 tools/check.py
# Without Node: explicitly skip UI checks, still run Python + trace integrity:
./tools/check.sh --python-only

# Focused checks remain available:
python3 -m unittest discover -s tests -v
python3 -m unittest discover -s tests -p 'test_web*.py' -v
node tests/test_web_ui.js
```

Tests use ephemeral loopback ports and never connect to a physical printer. Generated test files use the ignored project-local `.tmp/` directory and are cleaned up; do not use the system temporary directory for project work. No third-party dependencies are required. One integration test retains the uploader's existing three-second pause.

Web HTTP/workflow tests are grouped by feature in `tests/test_web*.py`, sharing
only a test-free ephemeral-loopback/fake-Orca fixture in `tests/web_helpers.py`.
Full checks fail visibly if Node is missing/older than18; no npm dependencies,
container build, native slicing or hardware action is added by the runner.
See [tests/README.md](tests/README.md) for test ownership and
[docs/REFACTORING.md](docs/REFACTORING.md) for the ordered maintenance plan/status.

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
- [docs/LAN.md](docs/LAN.md): explicit password-protected private-LAN sharing, shared workspace and cleartext HTTP limits.
- [docs/MANUAL_CONTROLS.md](docs/MANUAL_CONTROLS.md): virtual-only light/XYZ/extruder panel, safeguards and physical enablement blockers.
- [docs/STATUS.md](docs/STATUS.md): active status polling/default proxy startup, passive observer, source identity and stale-data limits.
- [docs/GX_PREVIEW.md](docs/GX_PREVIEW.md): observed GX/BMP thumbnail encoding and read-only extraction tool (not a GX generator).
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
- [docs/HOLE_COMPENSATION.md](docs/HOLE_COMPENSATION.md): per-edge XY hole adjustment, native offline geometry evidence and calibration limits.
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
