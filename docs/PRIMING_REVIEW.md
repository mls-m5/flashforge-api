# Placement-aware priming: exact-tool review and guarded candidate

## Finding and current scope

The line under/crossing the model is the **fixed startup purge/prime**, not the
ordinary brim around the first layer. A brim attaches near the first-layer
outline to improve adhesion; a skirt is a detached loop for priming. Deleting
brim alone does not remove this fixed purge. Draft02 still uses the fixed
X−25→55/Y−20→20 path independently of model placement.

The existing separate draft03 removes that fixed extrusion/Z0.2 descent and
uses native Orca skirt before optional brim/model. Its startup stages XY0/0 at
raised Z instead: this is a changed **physical start path**, not validated by
the user's earlier draft02 startup trial. Original02/03 profiles were not edited
in this milestone. Normal/proxy/LAN launchers still use02; no silent promotion.
No printer/proxy connection, uploaded candidate or hardware action occurred.

The exact supplied tool was sliced offline with native Orca2.3.0, manual centre
(to preserve the troublesome orientation), with both profiles. First-layer
line-centre diagnostics reproduced **21 startup/object XY segment intersections**
with02. With03, native skirt was first, fixed startup deposition was absent,
and there were no skirt/object or skirt/brim centreline intersections—also
with5mm brim and after scale/rotation/translation. Brim/object centreline
intersections were also zero (min gaps0.550699mm and0.547297mm for the examined
brim cases; bead contact is intentional and not simulated). This is an offline geometric
observation, not material/firmware/collision certification.

## Important new edge failure: native checks are not sufficient

An unguarded manual cuboid placement at X58 left the actual mesh within nominal
bounds (X48..68) but Orca exited0 and generated skirt centres as far as
**X72.105**, outside nominal±70. Raw capture/artifact retained unchanged at
`captures/priming-placement/20261115T110549Z-38bb77e6ec16`. The exploratory script
asserted rejection and failed: recording completion/native exit0 is not fit
approval. This supersedes any suggestion that the earlier136mm/exit206 example
proved every skirt/edge case is rejected. It did not.

A new **opt-in pre-publication guard** now prevents that candidate from becoming
a downloadable/saveable artifact. `./tools/start_skirt_test.sh` automatically
selects it with03 (`--check-priming`). Offline stays no-upload; optional
`--dummy-upload-test` still owns a fresh virtual dummy, never a proxy. This
launcher continues refusing proxy mode. Raw web/library/CLI flag is server/trusted
configuration, not an HTTP toggle. Ordinary02 behavior remains unchanged.

The guard requires:

- A nominal centred140×140×140mm rectangular machine matching the test grid.
- Supported tagged linear first-layer interpretation; native skirt is first.
- No custom startup XY deposition, no skirt crossing the first-layer object/brim
  or brim/object centreline crossing,
  and at least1mm nominal centreline separation when those groups exist.
- All reviewed startup/first-layer deposition centres within **±69mm**, a
  conservative1mm numerical margin inside nominal plate limits—not a measured
  head/clip/bead margin. Unknown/missing/oversized/ambiguous data fails closed.

It runs after native output but **before** `slicer_result`/publication. Guard
failure leaves no artifact, so even a checked combined Save + start cannot run.
No G-code is clipped, moved, rewritten or retried to hide the failure.

This is **not** a whole-job safety validator. It omits bead width, actual flow,
thermal/material response, homing/offset semantics, swept head/clip geometry,
nonlinear commands and later layers/overhangs. Separation is between declared
first-layer centreline paths; skirt may lie beneath the projection of a later
overhang. Nominal Z planes of startup/body can differ. Reports always retain
`safety_validated:false`, and published slicer results still say toolpaths are
not validated. A candidate passing this check is not physically approved.

## Read-only diagnostic tool and resources

```sh
python3 tools/check_priming.py path/to/output.gcode
./tools/start_skirt_test.sh
# CLI equivalent requires explicit local03 profiles/executable:
python3 -m finderlab slice model.stl --check-priming \
  --orca /path/to/Orca/AppRun --machine /path/to/draft03/machine.json \
  --process /path/to/draft03/process.json --filament /path/to/draft03/filament.json
```

The tool only reads plain G-code and prints derived JSON: first feature, segment
counts, nominal XY bounds, centreline intersections/gaps and candidate issues.
It never executes a command, reads printer storage, modifies raw input or
connects. Tool exit0 means a complete diagnostic report, not acceptance or print
safety; inspect `candidate_issues`. GX/binary, arcs/unsupported G frames, XYZ G92
resets, deposition across homing/offset frames, inch mode, unknown origins,
nonfinite/ambiguous fields and incomplete tag data fail without partial report.
Prefix mm before explicit G21 is an **assumption**, explicitly reported.
Extrusion modes/G92E and retract debt are tracked for nominal deposition, not
physical extrusion. First-layer scope stops at the second LAYER_CHANGE marker.

Bounds:8MiB/500k lines/4096 chars per line,100k deposited segments,2M total
segment-pair comparisons. The adapter runs the stdlib helper through its existing
process-group wrapper with512MiB virtual memory and15s wall (or smaller limits),
CPU ceiling+1, bounded logs/workspace, cancellation/reap and scratch cleanup.
The small JSON report is bounded64KiB and SHA-bound to the actual candidate
bytes. `priming_review` event/metadata records pass issues/bounds/hash before
publication or rejection; source/profile/geometry provenance remains separate.
Resource bounds are not an OS sandbox. Reports/coordinates can reveal model
geometry: keep raw artifacts/reports/captures private and ignored.

## Native guarded trial references

Under ignored `captures/priming-placement/`, with unchanged private02/03 source
hashes and zero printer sessions:

| Capture | Case | Nominal result |
| --- | --- | --- |
| 20261115T112829Z-e1cef3876420 |02, supplied tool, manual centre |21 startup/object XY pair intersections |
| 20261115T112831Z-4c665ea82681 |03, same tool/placement, no brim |Skirt first; zero crossings; min skirt/object gap3.386729mm |
| 20261115T112833Z-99f95bfaf857 |03, same tool, brim5 |Zero crossings; min skirt/brim gap3.393357mm |
| 20261115T112842Z-18d53dd5aa8d |03, scale0.75/Rz37°/X20/Y15, brim3 |Zero crossings; min skirt/brim gap3.378278mm |
| 20261115T112847Z-85d493e9eaf7 |03, cuboid X58, expanded skirt out of margin |Native slice succeeded, guard rejected, **no output artifact published** |

The earlier unguarded positive comparison runs are retained alongside the
edge failure as private historical evidence. Positive outputs retained final E delta−1.3mm
and resolved nominal Z components≤7mm/s; those diagnostics do not model homing.
No normal-profile swap or physical approval follows from these numeric trials.

Automated tests cover geometry comparisons/retract debt, malformed/unsupported
input and bounds, guarded fake-native publication/refusal, CLI/launcher wiring
and HTTP artifact/combined-save refusal. Host2.5 and rendered web/new-startup
acceptance remain user-run. Next decision: review the03 output on the host, then
explicitly choose whether/how to adopt the changed startup in the normal printer
workflow and plan a separately approved supervised empty-bed trial. Do not
silently switch a profile in response to a checkbox change.
