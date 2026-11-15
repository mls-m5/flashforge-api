# Standalone local Finder workbench

OctoPrint development is **paused**. The main page is now independent of
OctoPrint: `python3 -m finderlab web`. Python 3.11+ and the standard library are
sufficient for the page and printer transfer. No pip installation is needed.

## Model preview before slicing

Original STL/supported3MF geometry now has a separate solid-mesh view immediately
after file receipt, before Slice. Camera orbit/zoom/pan, wireframe, input
measurements and display-only centering are available in automatic mode. The
user accepted the initial view. Numeric uniform scale/XYZ rotation/XY movement
now draft a manual layout for explicit Slice, with Z automatically on bed and
Orca arrange0. Original files remain unchanged; completed slices stay immutable.
See MODEL_TRANSFORMS.md for source binding, bounded baking, native2.3 evidence
and fixed-purge/nominal-fit warnings. Gizmos/face picker/multiple models remain
future; new editor/browser/host2.5 acceptance is pending. Source identity survives Slice so the model can be compared with
the separate G-code result. See MODEL_PREVIEW.md for resource limits, isolated
3MF cache/conversion, token-protected GET and pending browser/GPU acceptance.

## Toolpath preview and direct button actions

The current server print artifact now has a local Three.js camera/height/travel
preview, automatically loaded after Slice or print-file receipt. No printer
storage fetch, model movement or printer command. It is bounded linear path
interpretation, not physical simulation, collision checking or print approval;
unsupported/unknown paths and mode assumptions are explicit. See [PREVIEW.md](PREVIEW.md)
for parser/render limits, vendored MIT license, tests and pending browser/GPU
acceptance. STL/3MF arrangement remains Orca's existing behavior.

At the user's request, **browser confirmation popups are removed**. Clicking
Slice/Save/Start/Cancel/Discard or a permitted monitor/virtual-control button is
now the explicit action; read the persistent warnings/target and exact Start
filename. The new start-after-upload checkbox is checked by default when server
job controls are enabled: the initiating button clearly says Save + start.
Uncheck for Save · no start. Backend composition requires confirmed save, healthy
release/complete recording and a fresh READY/exact-identity start; no uncertain
retry/automatic stop. See START_AFTER_UPLOAD.md. File receipt/slicing/GETs never
start jobs. API `confirm:true`, server policy
flags, fresh READY/save identity, one Start attempt, no uncertain retry and
Origin/token/auth/resource guards remain. CLI confirmations are unchanged.

## Optional trusted-LAN sharing

The default remains loopback. To share the full implemented workflow, use
`./tools/start_lan_web.sh` (no IP argument needed) after verifying the existing proxy
and closing FlashPrint. It explicitly enables Slice / confirmed Save / Start /
Cancel and status, with a per-run random password for every page/API route and
a private-IPv4 peer filter. All logged-in users share one file slot/printer;
physical manual controls stay locked. **HTTP has no encryption**: trusted home
network only, never router port forwarding/public tunnels. See [LAN.md](LAN.md)
for automatic local address selection, login, narrower subnet, firewall and acceptance limits. Nothing
is opened automatically by installing this change; the operator starts it.

## 3MF models (geometry only)

Drop `.3mf` and explicitly Slice just like STL. Core mesh geometry/build
transforms/units are converted to a bounded private STL derivative; embedded
project printer/filament/layer/start-code settings are **not passed to Orca**.
Our server profiles and typed web overrides still own those settings. No direct
3MF-to-printer Save. Assemblies/required extensions are rejected rather than
guessed; export STL if unsupported. See [3MF.md](3MF.md) for bounds and the
supplied tool's successful native offline trial (no printer sessions).

## Experimental placement-aware priming review

The separate `./tools/start_skirt_test.sh` now enables `--check-priming` with
private03: native skirt replaces fixed purge around the first-layer footprint,
also with brim/manual layout. The bounded helper refuses crossing/missing skirt
and out-of-nominal-margin deposition before exposing a downloadable/saveable
artifact. Native exit0 alone was observed allowing an out-of-bounds skirt; see
PRIMING_REVIEW.md for proof and limits. This is not whole-job/physical clearance
validation.03 still changes startup, stays offline/owned-dummy in this launcher
and refuses proxy mode in that isolated test workspace. The user has now
explicitly requested03 as the standard profile everywhere: ordinary offline,
owned-dummy, proxy and LAN launchers all select03 with the guard mandatory.
There is no fallback to02. Restart/re-slice; existing files are not rewritten.
Host/physical acceptance is not implied. HTTP cannot disable the guard.

## Printer status

**Changed default:** `./tools/start_proxy_web.sh` starts active status polling
on startup to the configured proxy. Close FlashPrint/other control clients
first; verify the proxy target. One firmware-gated session requests serial
M119/M105/M27 batches about one second apart. It yields its connection for
local printer operations and stops on errors/uncertain results without retry.
**Stop status polling** is not print cancellation; manual Start confirms a new
connection. `--no-monitor` disables startup polling while retaining manual Start.
The offline slicing launcher stays disconnected; owned-dummy mode polls only
its fresh simulator. Raw web CLI stays disconnected unless `--auto-monitor`
is given (`--enable-monitor` permits manual Start only).

The panel shows nozzle/bed temperatures, machine/motion state and reported byte
progress. In **passive mode** it reads existing proxy captures only, without
extra printer commands. The separate observer below is always passive. Samples are dated
individually; after10 seconds they are stale. Byte100% is not proof of finished
motion or remaining time. See [STATUS.md](STATUS.md) for limits and source
selection.

While FlashPrint already polls through the proxy, you can open a separate
read-only observer without restarting that connection:

```sh
./tools/watch_printer.sh
```

Open http://127.0.0.1:8001. Uploads, job controls and slicing are disabled in
this observer. Passive mode uses matching proxy-listener recordings under
`captures/`; the proxy launcher can
also take `--status-capture PATH` to an explicit run/root. The owned-dummy and
offline launchers do not automatically display physical-printer logs. The
status view cannot authorize or unlock any printer action.

## Manual-control panel (owned-dummy rehearsal only)

Light colour/off, XYZ single-step and extruder feed/retract now have a simple
panel, but **physical/proxy controls remain locked**. Existing Continuous-jog
captures do not establish small-step mode, thermal behavior or safe parser/mode
restoration. No manual G-code is encoded/sent in this milestone. Try it without
Orca or profiles: `./tools/start_control_panel_test.sh` (optional HTTP port as
one argument). The owned dummy is always fresh; ordinary endpoint/job flags
cannot enable physical manual controls. Counters/warm-nozzle simulation are
not position/temperature feedback. Revision/confirmation, busy/job/unknown and
bounded-counter guards are enforced server-side; lost responses never repeat
a step. See [MANUAL_CONTROLS.md](MANUAL_CONTROLS.md) for exact behavior and the
separately approved observations needed before physical enablement.

## Quick launch scripts

From the project root, two short executable Bash wrappers are available:

```sh
./tools/start_web_interface.sh
./tools/start_dummy.sh
```

Run them in separate terminals. The web wrapper starts the existing **read-only
native draft03 skirt slicing workflow** on 127.0.0.1:8000 (uploads and job controls remain
disabled); it requires the local Orca/profiles. It now prefers the extracted
`.local-tools/orca-2.5.0/AppRun` from the user's host-working 2.5.0 build,
otherwise the old `.local-tools/orca-slicer` when no 2.5.0 archive is present.
Direct FUSE AppImages are refused by this launcher: observed mounts failed
workspace inspection before Orca diagnostics were captured. If the archive
exists without extraction, it asks for extraction rather than silently falling
back to the incompatible older runtime. The chosen executable is printed;
`--orca PATH` explicitly selects another extracted launcher. Draft-02 output was reviewed
with 2.3.0, so a different build needs new offline output review, not an assumed
profile/physical-safety approval. The user reports 2.5.0 starts on the host;
it cannot run in the agent's older Debian environment. The dummy listens on
127.0.0.1:9000 and is not needed for offline slicing alone. The web launcher
labels that same target port but does not connect to it automatically.
Ctrl+C stops each process. Scripts also work when invoked by absolute path from
another directory. `./tools/start_web_interface.sh --port 8001` changes the HTTP
port; `./tools/start_dummy.sh --port 9001` changes the dummy port.

## One-command slicing and virtual upload test

Stop the previous web server (Ctrl+C), then run:

```sh
./tools/start_dummy_upload_test.sh
```

Open the printed URL (default http://127.0.0.1:8000), choose STL, Slice, then
click **Save + start … on dummy** with the default checked start-after-upload
option, or uncheck for **Save to dummy · no start**. Existing GX/G-code can also
be selected without slicing. The combined action starts only after final save /
healthy release/recording and fresh READY; save-only can still use separate
**Start saved file**. **Request cancel** cancels the virtual job. No G-code is
executed and file receipt/slicing alone never starts a job.

This creates its **own new dummy on an ephemeral loopback port** in the same
process; it does not reuse port9000, an existing proxy or browser-supplied target.
The target banner explicitly labels the owned dummy. No separate dummy script
is needed. `--port 8001` changes the HTTP port only. Ctrl+C/SIGTERM stops both;
virtual files disappear, but private web captures/artifacts persist in the
separate `web-data/dummy-upload-test/` workspace. Captures label the target as
emulated. The wrapper uses the same native Orca selection as the offline script.

Generated-output saving is enabled **only for this owned-dummy mode**, which
runs no G-code and connects to no hardware. This is a transport test, not a
waiver of profile/motion safety review or permission for a hardware print.
The normal offline launcher stays read-only; configured external endpoints keep
the existing upload/generated-output/job-control guards. CLI equivalent:
`python3 -m finderlab web --dummy` plus the trusted Orca/profile options.
`--dummy` refuses target/hardware/job-control overrides. Its own confirmed
Start/Cancel operate only on its new simulator. External configured endpoints
still require explicit `--enable-job-controls`; this dummy workflow does not
authorize hardware actions or validate the candidate's physical startup paths.

## Start with a fresh dummy

Terminal 1, from this repository root:

```sh
python3 -m finderlab mock --port 9000
```

Terminal 2:

```sh
python3 -m finderlab web --enable-upload --target-port 9000
```

Open **http://127.0.0.1:8000**, using the exact URL printed by the server.
Use `--listen-port 8001` if occupied. No printer connection or status polling
occurs on startup or page refresh in this low-level invocation without
`--auto-monitor`. Uploads are disabled without `--enable-upload`.
Without explicit `--lan`, the HTTP listener is restricted to loopback IPs.
LAN mode requires a specific192.168 interface, a private subnet peer filter and
the mandatory per-run password described above; wildcard binds remain rejected.

1. Drop one `.gx`, `.gcode`, `.g` or `.stl` file. This only stores it locally.
2. A print file can be downloaded/reviewed immediately. An STL requires the
   separately configured Orca stage below; clicking Slice never connects to a
   printer. The page shows a mesh/numeric layout editor before Slice and interpreted print-file toolpaths afterward.
3. Review the output and choose an unused ASCII remote basename. The suggested
   name and download attachment now derive from the input basename (`part.stl`
   → `part.gcode`), with bounded ASCII normalization for unsafe/non-ASCII names.
   Generated disk filenames use that same name inside a server-generated private
   slot; user input never selects a host path. The editable remote name remains
   separate from the exact server-recorded name used by a subsequent Start. With
   job controls enabled, the checked-by-default start-after-upload option makes
   the button **Save + start <name>**. Uncheck for **Save to Finder · no start**.
   Only that initiating click opens the requested operation, which can overwrite
   an existing remote file. Combined start requires healthy confirmed/finalized
   save and fresh READY; standalone Start/Cancel remain available.
4. Wait for **Final save confirmed**, not just all block bytes acknowledged.
   On unknown result, inspect logs and physical state, not a blind retry.
5. Discard removes current input/generated files, not the saved printer file
   or private captures. It does not cancel a print. Only one slot/job exists;
   choose another file after explicitly discarding the current one.

There are no discovery, pause/resume, direct heater/motion or arbitrary-command
endpoints. Explicit Start/Cancel endpoints are disabled by default as below. Existing GX bytes/previews remain unchanged; plain G-code is neither
wrapped in GX nor safety-validated. The fingerprint gate remains Finder
`V1.5 20170419`. Other firmware support is not inferred.

**Confirm port 9000 really belongs to your new dummy.** A loopback proxy can
reach hardware. To deliberately configure a non-loopback target, use
`--target-host IP --target-port PORT --allow-hardware --enable-upload` only for
an approved supervised trial. No agent hardware trial is part of this work.

## Manual web → recording proxy → printer setup

The short scripts do not scan for or verify a remembered printer IP. Check the
address on the printer/router first. The user recalled `192.168.0.39`; it is not
a verified or hardcoded default. No agent hardware action is performed here.
Stop the old web/dummy processes first; an occupied proxy port causes startup
to fail, not silently reuse an existing endpoint.

Terminal 1 (substitute the **confirmed** printer IP):

```sh
./tools/start_printer_proxy.sh 192.168.0.39
```

Terminal 2:

```sh
./tools/start_proxy_web.sh
```

This serves the page at 127.0.0.1:8000 and enables explicit Save to the proxy at
127.0.0.1:9000. The proxy's default upstream port is8899. **The web launcher now
connects for status on startup**; close FlashPrint/other control clients first.
To opt out, use `./tools/start_proxy_web.sh --no-monitor`. The proxy alone
connects upstream only when a client connects; it does not initiate polling. Existing
FlashPrint GX files can be saved with no automatic start/stop. Close competing
printer clients. The proxy records its own private capture as well as the web
capture in the separate `web-data/proxy-test/` workspace. **The proxy forwards
all commands unchanged; it is not a safety filter.** Verify its printed target
and running state before any browser action.

Optional explicit policy flags (not a recommendation to print the new candidate):

- `./tools/start_proxy_web.sh --enable-job-controls` enables separate confirmed
  Start/Cancel. Cancel is not emergency stop. A saved-file Start may heat/move.
- Generated-output Save remains blocked unless you deliberately add
  `--allow-sliced-upload`, after independent output/profile review. That switch
  does not validate startup homing, border clearance or firmware semantics. The
  current draft02 remains **not approved for physical printing**. The known
  startup-impact concern is unresolved; dummy success does not resolve it.
- `--port 8001` changes the web port. `--proxy-port 9002` changes its loopback
  target; pair it with `./tools/start_printer_proxy.sh IP --port 9002`.
  Upstream port override: `./tools/start_printer_proxy.sh IP --target-port 8899`.
- `./tools/start_proxy_web.sh --check` checks local paths only, without starting
  a listener or contacting anything. Ctrl+C stops each running service. A print
  can continue after disconnect, and no automatic cancel is sent on shutdown.

For a local-only rehearsal, start a **fresh** separate dummy on a deliberate
port, e.g. `./tools/start_dummy.sh --port 9001`, then use
`./tools/start_printer_proxy.sh 127.0.0.1 --target-port 9001`. Do not assume that
an already occupied loopback port is a dummy instead of a hardware proxy.

## Optional explicit Start and Cancel

To enable the separate buttons, first test with the new dummy:

```sh
python3 -m finderlab web --enable-upload --enable-job-controls --target-port 9000
```

In Podman, append `--enable-job-controls` to the arguments after the image name.
It is independent of `--enable-upload`; neither flag overrides the non-loopback
hardware guard or experiment approval. Each button click is the explicit action; no recurring browser confirmation
popup is shown. **Start may heat/move a physical printer behind a proxy.** No new
agent hardware trial is authorized or performed by adding these controls.

- **Start saved file** uses only the exact server-recorded basename from this
  slot's confirmed save. A per-save ID binds confirmation to that save so another
  tab cannot silently replace the reference. Editing the remote-name input after
  Save cannot redirect Start. A new firmware-gated session rechecks READY before
  M23. There is at most one Start attempt per slot; failed/uncertain attempts are
  not retried. Discard/restart loses the reference rather than guessing it.
- Save IDs do not lock or read back remote contents: another client can overwrite
  a filename on the printer. Close competing clients and start only reviewed,
  known-safe files. A successful save or slice is not a motion-safety certificate.
- **Request cancel** sends a separately confirmed M26 to the configured target,
  including jobs started outside this page; no local file is required. This is
  **not an emergency stop** and an ACK does not prove READY, stopped motion or
  cooled heaters. Check the physical printer. A deliberate new confirmation may
  send another cancel; the server/browser never automatically retries it.
- All operations share the single-job lock. Cancel is unavailable while another
  local operation is active; it is not injected into an upload's binary stream.
  Shutdown and failures never send automatic M26. Physical controls remain
  necessary for emergencies. Active monitoring uses the same network lock,
  releases its session before these operations, and stops after uncertain I/O.
  Neither active nor passive snapshots guarantee physical state.
- Start/cancel result and original save confirmation are separate facts. Lost
  replies report UNKNOWN; a failed start does not erase the confirmed save.
  Subsequent release/logging failures are shown separately. Context/loopback
  tests validate wiring, not physical start/cancel dynamics or safety.

## Orca is optional; native experimental slicing is not print approval

The page uses the existing resource-limited, shell-free Orca adapter. It does
not bundle a printer profile, edit the existing local draft, substitute Marlin,
turn off validity checks or pretend the Sailfish incompatibility is fixed.
Installed Orca 2.3.0 rejects the current draft's `gcode_flavor=sailfish`;
2.5.0 source also excludes it from accepted values. See
[ORCA_FINDER_DRAFT_01.md](ORCA_FINDER_DRAFT_01.md). A separate offline dialect/
profile decision is still needed before a useful native Finder slice can be
claimed. **The initial page is usable with existing FlashPrint GX files now;
STL → safe Finder toolpaths is not yet solved.**

The user subsequently authorized a separate **offline Marlin-emission draft 02**.
Native 2.3.0 now slices a generated cube and the supplied holder and the native
HTTP Slice/download path was checked, with uploads/job controls disabled.
Extrusion resets, final retraction and a slow Z layer-change hook address the
identified numeric issues, but G21/M82/M118 behavior and physical homing/clip
clearance remain unresolved. See [ORCA_FINDER_DRAFT_02.md](ORCA_FINDER_DRAFT_02.md)
for private artifact paths and a **read-only slicing-page invocation**. On this
workspace, `python3 tools/start_offline_web.py` is the short launcher for that
native experiment; it never enables uploads or job controls. Original
profiles are unchanged. Do not enable generated-output upload/start just because
this candidate slices successfully.

With your own trusted, self-contained and separately reviewed JSON profiles:

```sh
python3 -m finderlab web \
  --orca /absolute/path/to/orca-slicer \
  --machine local-profiles/reviewed-machine.json \
  --process local-profiles/reviewed-process.json \
  --filament local-profiles/reviewed-filament.json
```

The paths above are placeholders, not provided working profiles. See
[SLICING.md](SLICING.md) for required profile fields, CLI/native runtime setup,
limits and provenance. No path/executable/profile or arbitrary Orca argument is
accepted through HTTP. Drop STL (millimetres), explicitly Slice, then download
its generated plain `.gcode` for offline inspection. Native diagnostic excerpts
are bounded and displayed as text; private captures retain original output.
Slicing success never triggers an automatic save or print.

Saving generated output is **blocked by default** even when regular print-file
uploads are enabled. Only after separate profile/output review may an operator
also supply `--allow-sliced-upload` and `--enable-upload`. This is an explicit
policy opt-in, not a toolpath safety certificate. The browser still requires a
separate confirmed Save; a GX remote-name override for generated G-code is
rejected. Native code/profiles are trusted, not sandboxed: the resource wrapper
limits jobs but cannot deny arbitrary filesystem/network access to a malicious
slicer. Use only trusted local models on this experimental page.

## Podman on Linux

No OctoPrint setup or printer profile wizard is involved:

```sh
podman build -f docker/web.Dockerfile -t localhost/finderlab-web .
podman volume create finderlab-web-data
podman volume create finderlab-web-scratch
podman run --rm --name finderlab-web --network host \
  --cap-drop=all --security-opt=no-new-privileges \
  -v finderlab-web-data:/app/web-data:U \
  -v finderlab-web-scratch:/app/.tmp:U \
  localhost/finderlab-web --enable-upload --target-port 9000
```

Start the host dummy separately as above. Host networking makes its loopback
port reachable; the page itself binds only `127.0.0.1:8000`. `:U` changes
ownership inside these dedicated named volumes; do not substitute production
volumes/directories. Stop with `podman stop finderlab-web`; private data persists.
Rebuild the image after code changes.

The image contains **no Orca executable/native GUI libraries/profiles**. Use the
native Python invocation for initial Orca experiments. A pinned, tested slicer
container requires further work; mounting an executable alone is not sufficient
if its shared libraries are missing. Podman/Docker is unavailable in the agent
environment, so image build/runtime remain unverified.

The default `docker-compose.yml` now runs the standalone page (uploads disabled).
For a Compose provider, use `podman compose up --build` or
`docker compose up --build`. To enable transfers, deliberately add the desired
`--enable-upload --target-port PORT` command to that service. The old OctoPrint
example is preserved separately at `compose.octoprint.yml`; do not start it as
part of the standalone workflow.

## Storage, HTTP and failure boundaries

- `web-data/` is private and Git-ignored. Use a dedicated folder; `--data-dir`
  selects it; if changed, keep that location out of Git/build contexts yourself.
  One process holds its workspace lock. State is in-memory only;
  restart does **not** resume jobs or infer remote state. Interrupted files/logs
  remain on disk and count against quota; inspect/archive them locally.
- One resident file, one operation, no queue. STL ≤64 MiB; print/generated file
  ≤8 MiB; incoming file deadline 60 s. Header/JSON deadlines 10 s, headers
  ≤16 KiB, JSON ≤2048 bytes, at most 16 HTTP clients. Connections close after
  one request; no chunked upload, multipart, pipelining or Expect support.
- Workspace admission is conservatively bounded to 256 MiB and 4096 entries:
  each operation reserves a worst-case capture/output budget before starting.
  This includes stored files/captures, not the Orca adapter's separate bounded
  scratch workspace under project `.tmp/` or unrelated writers. Capture streams
  are capped at 64 MiB per operation; no automatic log deletion/rotation.
- Save has an overall 900-second deadline plus transport timeouts. Shutdown
  cancels local tasks/process groups and closes sockets, never sends a printer
  cancel. Partial/unknown remote files may remain. An unknown save cannot be
  repeated in the same slot; inspect first, then explicitly discard/reset.
- Raw captures and generated output can contain model bytes and identifiers.
  Do not publish them or whole runtime volumes. `complete` describes recording,
  not save/slice success. Save confirmation and later release/log failure are
  distinct facts; a confirmed save is not erased by a later error.
- Strict Host matching resists DNS rebinding; mutating requests require exact
  same Origin plus a per-run token fetched by the page. No CORS permission is
  emitted. CSP restricts scripts/styles/connections to this origin and rejects
  framing. No browser-supplied target paths, addresses or native options.
- This is a small HTTP/1.1 workbench, **not a production web server**.
  Opt-in LAN mode has one shared Basic login but no TLS or individual accounts.
  LAN credentials protect every asset/API response; fixed Host and Origin/token
  checks remain. All logged-in users/local processes/extensions/native profiles
  are trusted. Never forward its port or use a public tunnel/reverse proxy;
  private-IP filtering does not establish trust. See LAN.md for cleartext and
  shared-slot limitations. No security-sandbox claim is made for native STL parsing.

## Quality controls: brim, layer height and XY hole compensation

The Slice section offers **Layer height**, **Brim**, and independent **XY hole / contour compensation**.
Layer/brim default to **Use server profile**; both compensation fields default to
**0 mm (off)**, or clear either field to keep its server profile value. Controls apply only to the next
explicitly confirmed Slice. They do not reslice, save, start or change a running
print automatically. Existing GX/G-code files are never rewritten.

- Layer choices in the page: profile, 0.12, 0.18, 0.20, 0.24, 0.28 mm. The typed
  API accepts only finite numeric 0.08–0.28 mm or null (profile); this bounded
  UI policy is aimed at the current 0.4 mm nozzle experiment, not a certificate
  of compatibility with arbitrary machine/nozzle profiles. Orca checks remain
  enabled. **First-layer height stays in the server profile** (draft02:0.27).
- Brim: profile, Off (`no_brim`, width0), Outer (`outer_only`, width1–10 mm,
  UI initially5 mm). Width is ignored for profile/Off. The existing profile's
  brim/object gap stays unchanged (draft02:0.1 mm); it is shown after slicing.
- XY hole compensation: finite **−0.5 to +0.5 mm per edge**, numeric UI initially0.
  Positive enlarges internal XY openings: **+0.2 mm per edge increases a circular
  hole's diameter by about0.4 mm**. Negative shrinks them. This is not a percent
  scale or a diameter input. Empty/null means profile; omitted API/library key
  also preserves it. Explicit0 disables an existing nonzero profile setting.
  Only `xy_hole_compensation` in the private process snapshot changes via this
  field; outer-contour compensation has its own independent field.
  Holes in other orientations, first-layer squish and material/flow errors may
  need different calibration. Enlarging openings can thin/remove narrow walls;
  inspect the generated output and test a small part before relying on fits.
- XY contour compensation: same numeric bounds/default/profile semantics as
  holes, using `xy_contour_compensation`. **−0.2mm per edge shrinks outer width /
  diameter by about0.4mm**; positive enlarges. This is not global scaling or Z
  correction. Outer−0.2 and hole+0.2 together can thin walls by about0.4mm.
  Native offline sign/independence checks are in HOLE_COMPENSATION.md; printed
  dimensions still need calibration. Both applied offsets are displayed.
- A 5 mm outer brim is a reasonable experiment for lifting edges, not a
  guarantee. It consumes bed area/material, needs removal and can mark the
  bottom edge. Keep the bed clean/level and avoid drafts. Cold room conditions
  may contribute; do not infer that extra nozzle heat alone fixes adhesion.
- Brim expands the generated footprint. Orca may reject a plate that no longer
  fits. Review its placement/preview in a slicer if needed: the page has no
  collision/toolpath-preview validator. A wider brim can intersect a fixed
  custom purge line; this is model/profile dependent, not automatically solved.
- Temperature, filament flow, machine/start/end templates and **retraction
  remain untouched**. The user's request to defer final-retract tuning is
  preserved. No extra end E move is introduced.

Applied values are displayed separately from controls after success and remain
bound to that artifact. To change a completed slice, discard/reselect the STL
and Slice again. Restart/current-slot resets are not saved global quality
preferences. A newly selected print file does not inherit G-code edits.

The API accepts `settings` only on confirmed `/api/slice`, for example:

```json
{"confirm":true,"settings":{"layer_height":0.12,"brim":"outer","brim_width":5,"xy_hole_compensation":0.2}}
```

Unknown fields, strings in numeric fields, booleans, non-finite values and
out-of-range numbers are rejected before native execution or printer access.
No executable/path/profile/template or arbitrary Orca JSON key becomes an HTTP
parameter. Only the allowlisted process fields are changed on the already
validated **private workspace copy**, never the original profiles.

Each slice records the normalized settings, exact process overrides, original
process hash, effective process hash and applied layer/first-layer/brim/gap /
hole/outer-contour values in its private capture. Effective quality also appears in cached state.
With all overrides omitted/profile, profile bytes and their hash are preserved
exactly. The UI's default explicit hole0 is an override, even if geometrically
identical to the current draft02 value0; only its private snapshot is serialized.

### Native offline settings trial

Native Orca2.3 on generated20×20×5 cube, layer0.12 / outer brim5:
`captures/quality-ui/20261114T200743Z-4ddfcec1d4f5`. Actual output contains Brim
paths, body endpoints expand from about±9.8 to±14.3, first-layer0.27/gap0.1
remain unchanged, final requested E delta remains−1.3 mm and resolved nominal Z
component is at most7 mm/s. All three source profile hashes stayed unchanged;
recording finalized with zero printer sessions. This verifies native option
wiring, not physical adhesion/quality or every model placement. Host2.5 GUI
and printed brim quality still need user validation. No hardware was contacted.

## Separate dynamic-priming experiment

The user subsequently explicitly selected this same guarded03 skirt profile
for all ordinary/proxy/LAN launchers; the earlier draft02 startup evidence does
not physically validate the changed03 path. Re-slice after restarting the backend.
A new `./tools/start_skirt_test.sh` selects independent **draft03** for offline
Slice/download review: native Orca skirt surrounds the arranged model/brim,
instead of a fixed purge line across the print. Skirt remains enabled even with
brim to retain a distinct priming phase. Start staging changes, so this is not
a physical-print approval inherited from the cube trial. The launcher refuses
proxy mode; optional `--dummy-upload-test` is virtual only. No existing output
or original02 profile is rewritten. Native2.3 trials and remaining host2.5 /
physical checks: [ORCA_FINDER_DRAFT_03.md](ORCA_FINDER_DRAFT_03.md).

## Help text versus slice result

Orca's help text is a normal capability probe, not a failure by itself. Once the
actual slice command starts, the displayed excerpt is cleared so a silent
successful slice does not leave only old help text. Raw help remains intact in
the private capture. The Slice section now shows explicit checking/slicing/
completed status and offers the generated artifact for download. An operation
error is displayed even when Orca produced no stdout/stderr. Completion means
file generation, **not physical print approval**.

## Narrow local API

All POSTs require `Origin: http://<exact printed authority>` and
`X-Finder-Token` from GET `/api/config`. Files use `application/octet-stream`;
other POSTs use `application/json`. Target/executable/profile/path overrides
are never accepted. GET config/state are local-only cached reads, not printer
queries. A successful action response means accepted/current state, not final
save or slice success; poll `/api/state` while `busy`.

| Method/path | Meaning |
| --- | --- |
| GET `/api/config` | Per-run token, fixed endpoint, capabilities and limits |
| GET `/api/state` | Current slot/job state and bounded private diagnostic excerpt |
| GET `/api/manual-state` | Cached virtual counters/capability and local busy/job guards; no printer query |
| POST `/api/manual` | Confirmed typed/revision-bound virtual intent, owned dummy only; never wire G-code |
| GET `/api/printer-status` | Cached active snapshots or passive derived observations; no printer query |
| POST `/api/monitor` | `{"enabled":true,"confirm":true}` starts permitted status polling; false stops monitoring only |
| POST `/api/file?name=NAME` | Bounded raw bytes into empty slot; no slicing/printer connection |
| POST `/api/slice` | `{"confirm":true,"settings":{...}}`; optional typed quality settings, offline Orca only |
| GET `/api/model` | Original STL / geometry-only3MF derivative, source ETag, optional If-Match; X-Finder-Token required; never invokes Orca/printer |
| GET `/api/artifact` | Idle-slot print file download; ETag and optional If-Match identity, fixed safe attachment name |
| POST `/api/save` | `{"confirm":true,"remote_name":"sample.gx"}`; upload only |
| POST `/api/discard` | `{"confirm":true}`; remove idle slot files, retain logs |
| POST `/api/start` | `{"confirm":true,"save_id":"ID from cached state"}`; gated exact saved file, fresh READY check |
| POST `/api/stop` | `{"confirm":true}`; gated cancel request, not emergency stop |

Preview module/worker and pinned Three.js assets are explicitly allowlisted
under the same authentication; no runtime CDN or arbitrary static directory.
There is no general filesystem browser or raw capture download endpoint. The
printed private capture path is for deliberate local inspection.

## Local application trials (not hardware evidence)

Actual stdlib HTTP-client trials against freshly started ephemeral services:

- Supplied 3668165-byte GX → HTTP file endpoint → explicit Save → new dummy:
  exact byte equality, 896 frames, only M601/M115/M119/M28/M29/M602 and no
  virtual print. Private capture:
  `web-data/manual-gx/captures/20261114T132526Z-4112e567c689`.
- Native installed Orca 2.3.0, unchanged private Finder draft, generated binary
  review cube → HTTP Slice: expected Sailfish validation failure, bounded native
  diagnostic visible through cached state, no output artifact or printer
  sessions. Private capture:
  `web-data/native-profile-check/captures/20261114T132526Z-fe43872dc961`.
  An initial one-triangle ASCII sample failed model loading first (capture
  `20261114T132451Z-3249c3aae033`); it was replaced with the generated binary
  cube for the profile check. Neither run changed the profiles or contacted a
  printer. This is a failure-path trial, not successful native slicing.

Raw files/geometry and captures remain ignored. These trials exercise HTTP and
native adapter behavior, not a real browser rendering or physical compatibility.

## Checks and remaining acceptance

```sh
python3 -m unittest discover -s tests -v
node tests/test_web_ui.js
node tests/test_passive_status_ui.js
node tests/test_active_status_ui.js
node tests/test_manual_ui.js
node tests/test_toolpath_worker.js
node tests/test_preview_ui.js
node tests/test_toolpath_view.js
node tests/test_model_worker.js
node tests/test_model_preview_ui.js
node tests/test_model_transform.js
node tests/test_model_editor_integration.js
node tests/test_start_after_upload_ui.js
```

Tests use fresh ephemeral HTTP/TCP loopback endpoints, generated bytes and a fake
Orca executable. They exercise browser/server transfer separately from save,
exact payload/hash/command order, save without start/stop, separate confirmed
job controls with stale-ID/repeat/unknown guards, explicit gates, origin/token/
Host checks, truncated/oversized files, busy/quota/locking and slicing outcomes.
Node checks use a minimal DOM model, not a rendered browser. Native experimental generation has a separate recorded trial; a print-approved
Finder profile, actual browser drag/drop and container acceptance still need
manual validation. No physical printer is used or authorized by these checks.
