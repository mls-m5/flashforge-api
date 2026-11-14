# Finder offline draft 02 — native slicing succeeds, NOT approved for printing

## Authorization and scope

The user explicitly approved a separate **offline** Orca/Marlin-emission
experiment, prioritizing startup edge collisions and excessive end extrusion.
This changes the emitted-code candidate, **not the printer firmware**. No
printer, existing proxy or hardware endpoint was contacted. No generated file
was uploaded or started. No validity checks were disabled.

The original `local-profiles/finder-offline-01/` and mounted Orca configuration
remain unchanged. New, private files are under ignored
`local-profiles/finder-offline-02/`. The original flattened Orca source lineage,
AGPLv3 license and upstream attribution are preserved in its `originals/` and
base `provenance.json`; `experiment-02-provenance.json` records the new changes.
Selected FlashPrint reference values are facts from
[FLASHFORGE_PROFILE_REVIEW.md](FLASHFORGE_PROFILE_REVIEW.md), not a copied vendor
profile or a claim of permission to redistribute that profile.

**This is a numerically reviewed CLI candidate, not a validated Finder profile,
GUI-import bundle, collision certificate or permission to print.** No reviewed
profile is shipped in Git. Raw geometry, outputs and private reports stay local.

## Staged native Orca 2.3.0 trials

Every row below is an actual native run via the bounded `finderlab slice`
adapter, not the fake test executable. All captures finalized with no printer
sessions and `slicing_confirmed: true`. This asserts geometry generation only.

| Stage / input | Private capture under `captures/finder02/` | Outcome |
| --- | --- | --- |
| A / generated 20×20×5 mm cube | 20261114T142221Z-c61da6d51f50 | Flavor changed from rejected Sailfish to explicit Marlin candidate, plus identity references only; 90990-byte output |
| B / cube | 20261114T143057Z-f7b2c0ae1c8b | Reference-based settings and explicit E/start/end ownership; 81654-byte output |
| B / supplied holder STL | 20261114T143134Z-70885c543416 | Slices, but mixed XYZ travel nominal Z component reaches 12.915967 mm/s; **not accepted as final candidate** |
| C / cube | 20261114T143309Z-db97bab578a2 | Layer-change Z split; 83313-byte output |
| C / holder | 20261114T143310Z-a9d34d43af84 | Layer-change Z split; 4903637-byte output |

A separate actual HTTP test sent the generated cube to a freshly started
loopback workbench, explicitly sliced with native 2.3.0 and downloaded its
83313-byte artifact. Capture
`web-data/finder02-native/captures/20261114T144346Z-167968ea37f7` finalized with
no printer sessions. Uploads and job controls were disabled; an attempted Save
was correctly refused (409). This tests HTTP/native wiring, not rendered-browser
interaction or physical printing.

## Candidate configuration and deliberate differences

The current three JSON files are **stage C**; stage A/B snapshots are retained
privately for comparison.

- Nominal 140×140×140 mm, centered XY ±70. The user subsequently confirmed a
  0.4 mm nozzle and PLA; this is user-reported, not independently measured.
  Filament diameter 1.75 mm remains an assumption. Nominal dimensions are not a
  measured origin/clearance certificate.
- User/requested and FlashPrint Standard comparison: layers 0.18 / first 0.27 mm,
  nozzle 220, bed 0. Retraction 1.3 mm at 30 mm/s in/out; 2 walls, 3 top/bottom
  layers, 15% infill; first layer 10 mm/s, outer wall 30, inner wall 42,
  sparse infill 60, travel 80, dedicated Z travel 7.
- Flow ratio 1.09 is an explicit comparison hypothesis derived from FlashPrint's
  extrusionRatio, **not a proven one-to-one conversion or filament calibration**.
  Orca line widths and rectilinear infill are not exact FlashPrint geometry.
- Machine limits/acceleration emission, firmware retraction, pressure advance,
  object-exclusion commands, brim/skirt and automatic prime tower remain off.
  Generic inherited estimation/clearance properties are not hardware measurements.
- M73 progress emission is disabled through Orca's `disable_m73` setting because
  it was an extra unverified command in stage A; this is **not** `--no-check` or
  removal of validity checks. Outputs are not postprocessed/re-written.
- Homing/heating/current prefix and fixed purge come from the working reference,
  with explicit G92 E0 before priming and at the body handoff. Explicit M82
  states the candidate's intended absolute E mode, but its Finder support is
  still unverified. The generated body also emits M82 and G21.
- M118 is still omitted. Its requirement/semantics have not been established;
  no guessed model bounds or old model-specific M118 constants were inserted.

## Startup and end extrusion: what the files actually request

The previous Prusa sample's copied prime ended at absolute E17.4017 without a
reset; its first E−2 requested a −19.4017 mm transition. The candidate explicitly
resets E at the handoff. Its first body retraction is −1.3 mm from that zero,
not a nineteen-millimetre retract. Slicer-emitted resets/restarts were inspected:
subsequent E1.3 restores the retract after a G92 E0; G92 is a coordinate reset,
not filament motion.

The old Prusa end moved E415.17445 → E778.4812: **+363.30675 mm** under its
declared absolute-E intent. The stage C cube and holder instead end with a
slicer-owned **−1.3 mm** retract at F1800, then a coordinate reset. Their custom
end has **no E move and no fixed G1 Z/XY park**. Thus it does not copy a final
absolute E value or model-dependent Z/XY destination from another job.
The largest positive E-only move in each stage C file is +1.3 mm (unretract).
There is no diagnosed large positive end E-only step in these outputs.

This proves a difference in intended numeric code, not the physical firmware's
interpretation. The retained end homing/offset/motor suffix
(G162 Z → G28 X Y → M132 → M652 → G91 → M18) is still unmodeled physical motion.

## User-reported startup impact clarification

After this experiment the user confirmed 0.4 mm nozzle / PLA and described the
previous impact as occurring at or near an X extreme (maximum versus minimum
unknown), possibly a straight downward motion after leaving home. There is no
video, raw motion trace, exact command/line identification or direction/frame
measurement. This is a **user-reported symptom**, not a confirmed root cause.
The word downward does not identify the sign of logical Z on a moving-bed
machine.

The old Prusa file, working FlashPrint reference and current candidate all
contain G28/M132, then G1 Z50 F420, then G161 X Y F3300. Later, after an XY
staging command, each requests G1 Z0.2 F420 for priming. The old Prusa staging
point is X5/Y30; the reference and current candidate use X−25/Y−20. These are
code observations, not proof of the actual physical head location. An impact
near X home during a vertical move may involve homing/offset/staging or physical
clearance; the current nominal XY-bound check cannot distinguish those causes.

Do not diagnose this as simply an oversized bed or assume that slower layer
changes fixed startup. Stage C addresses **body layer-change speed**, not these
retained startup homing/Z moves. Do not change home/origin commands on a guess
or repeat the failing print for diagnosis. Next useful clarification is whether
the head had visibly moved from the X end position onto the plate before the
vertical motion, and whether this happened before the first purge extrusion.
No new hardware attempt is authorized by this clarification.

## Coordinates and layer-change Z finding

| Stage C diagnostic | Cube | Holder |
| --- | --- | --- |
| Full explicit G0/G1 X bounds | −25 … +55 | −49.8 … +55 |
| Full explicit G0/G1 Y bounds | −20 … +20 | −20 … +20 |
| Model-body XY bounds | ±9.8 / ±9.8 | ±49.8 / ±14.8 |
| Model-body Z endpoints | 0.27 … 4.95 | 0.27 … 49.95 |
| Last E delta | −1.3 mm | −1.3 mm |
| Max resolved nominal Z component | 7 mm/s | 7 mm/s |

Explicit G0/G1 Z endpoints include the reference's startup Z50 and prime Z0.2.
First-layer 0.27 and final 4.95/49.95 are actual generated coordinates, not a
claim that they reproduce the FlashPrint first layer 0.280 / final 50.000.
XY values describe **commanded nozzle endpoints**, not nozzle/head swept volume,
actual origin, frame/clip clearance or homing routes. The purge reaches X55,
15 mm inside a *nominal* +70 limit; that is not a physical clearance measurement.

A scalar F4800 on a combined XYZ move does **not** mean Z travels at 80 mm/s.
The linear-path nominal component is F/60 × |ΔZ|/length(XYZ). Stage B's holder
nevertheless reached **12.915967 mm/s** on a short mixed segment despite the
travel_speed_z=7 setting. Relying on that setting or assuming a firmware clamp
would hide the issue.

Stage C changes only the layer-change hook relative to B:

```gcode
; after slicer-owned retract and E reset, before XY travel
G1 Z{layer_z} F420
```

Native macro expansion and actual ordering were inspected. The Z step occurs
separately before XY travel; any following combined XYZ command has already
reached the same Z. Resolved Z components in both current outputs are at most
7 mm/s. This is a profile/template change, not output editing or a firmware-limit
command. It must be rechecked for other slicer versions, settings and models.
Two startup Z segments have unknown preceding positions after unmodeled homing/
offset commands; their requested pure-Z F420 does not prove a safe physical path.

## Local files and offline reproduction

Private retained artifacts:

```text
local-profiles/finder-offline-02/
  machine.json, process.json, filament.json  # current stage C, not print approved
  stage-a/, stage-b/                        # previous snapshots
  experiment-02-provenance.json
  originals/, provenance.json               # source lineage/license retained
  review/cube-20x20x5.stl
  review/cube.gcode, review/holder.gcode      # DO NOT PRINT
  review/*-review.json, review/summary.json  # diagnostics, not approval
```

To generate a new file without any printer connection:

```sh
mkdir -p .tmp
python3 local-profiles/finder-offline-02/slice.py MODEL.stl \
  --output .tmp/new-offline-review.gcode
python3 -m finderlab review .tmp/new-offline-review.gcode \
  > .tmp/new-offline-review.json
```

The wrapper calls `slice` only, refuses existing output through the adapter,
and defaults to the local 2.3.0 launcher. It does not expose upload/start flags.
The private profile directory is not supplied by a fresh public clone.

For a **read-only slicing page test** on this workspace, the short launcher
checks the local paths, uses a separate `web-data/offline-test` workspace and
always leaves all printer actions disabled. It prefers the extracted
`orca-2.5.0/AppRun` from the user's host-working Ubuntu2404 2.5.0 build and prints
the selected path. Direct AppImage FUSE mounts failed workspace checks on the
host, so the launcher now requires extraction (see ORCA_INSTALL.md).
`--orca PATH` selects another extracted launcher; the old `orca-slicer` fallback
is used only when neither 2.5.0 extraction nor its archive is present.
The 2.3.0 findings above do not validate a new 2.5.0 output; review it offline
again before any separate physical decision:

```sh
python3 tools/start_offline_web.py
# If port 8000 is occupied:
python3 tools/start_offline_web.py --port 8001
# File preflight only, without starting anything:
python3 tools/start_offline_web.py --check
```

Open the printed loopback URL, choose the listed test cube (or your STL), then
Slice and download for review. Ctrl+C stops the server. This runs natively,
not in the Podman image; Orca runtime libraries still need to work on the host.
Private profiles/executable must already exist locally; `--check` only checks
files, not native loading or profile/motion safety. No arbitrary flags are
forwarded by the launcher.

For the originally reviewed 2.3.0 executable, explicitly select
`--orca .local-tools/orca-2.3.0/AppRun` (requires compatible host libraries).
The earlier observed expanded 2.3.0 invocation is:

```sh
python3 -m finderlab web --orca .local-tools/orca-slicer \
  --machine local-profiles/finder-offline-02/machine.json \
  --process local-profiles/finder-offline-02/process.json \
  --filament local-profiles/finder-offline-02/filament.json
```

Do **not** add `--enable-upload`, `--allow-sliced-upload` or
`--enable-job-controls` for this offline test. STL drop → explicit Slice →
download/review is available; printer actions remain disabled.

## Remaining physical blockers / next review

- Nozzle 0.4 mm and PLA are now user-confirmed. Confirm filament diameter and
  retain flow/cooling/speed as uncalibrated assumptions for this spool/printer.
- Confirm M82/G21 behavior and M118 necessity on the observed firmware. These
  are the two added command codes versus the supplied working FlashPrint file;
  command parameters (e.g. M106 S PWM), origin, templates and trajectories also
  need review. A command-set match alone is insufficient.
- Physical execution of this plain `.gcode` output is not established by byte
  transfer support; a GX wrapper/thumbnail generator is not provided. Clarify
  the file/format path used for earlier Prusa prints before planning execution.
- Inspect the actual homing/offset sequence and plate/clip/head clearance.
  Diagnostics cannot show that G28/G161/G162/M132 will avoid a collision. A
  paired FlashPrint export of the same small cube, and a precise description of
  which previous startup move hit the edge, would reduce uncertainty without
  running this candidate on hardware.
- Only after the offline differences/blockers are resolved should a separately
  approved, supervised small-model physical trial be planned. No working/printer
  profile, emergency-stop guarantee or permission to print is conferred here.

## Diagnostic tool limitations

`python3 -m finderlab review FILE.gcode` (or the observed GX container) reads
only and reports modal endpoints, E deltas, references, unmodeled homing and
warnings. `--assume-absolute-e` labels the necessary intent assumption for the
FlashPrint/old Prusa examples without explicit M82/M83; it does not establish
actual firmware modes. It does not evaluate templates or execute commands.
Unknown origins/modes stay unresolved. Mixed XYZ feed is projected only for
resolved linear segments; homing/offset paths, acceleration, clips, nozzle/head
volume and firmware-specific behavior remain unknown. Missing alerts are **not**
a safety result. Tests use synthetic vectors, including the diagnosed +363 mm
end and split-vs-combined Z case, not private model bytes.
