# Single-model scale, rotation and XY placement

## Implemented workflow

The user accepted the original mesh preview and requested geometry editing next.
The model section now offers **uniform scale1–1000%**, **XYZ rotation−360..360°**,
**XY bounding-box centre−70..70mm**, +90° buttons, Center XY, Reset/automatic
arrangement and Show plate. These are numeric edits, not mouse gizmos. Camera
drag still orbits/pans the camera. Original STL/geometry-only3MF remain supported;
a multi-build3MF is one flattened group, not independently selectable objects.

Editing a number enables **Use manual transforms/placement for next Slice**.
The shaded mesh updates immediately and shows transformed dimensions. Manual
mode starts a whole-plate camera view; Fit camera can focus the model again.
Invalid input hides stale mesh; nominal out-of-bounds geometry is visible with
an error and cannot Slice. Uncheck manual mode or Reset for the prior automatic
arrangement workflow. Nothing is sliced, saved, heated or started by editing.

On explicit **Slice**, the exact source-bound typed draft is sent to the server.
The server transforms a **private STL derivative**, then requests
`--arrange 0 --orient 0 --ensure-on-bed`; the requested XY placement is not
silently replaced with auto-arrange. Ordinary CLI/library/web slices without a
manual transform keep `--arrange 1` unchanged. Model Get/Reload still serves the
original input geometry, not a modified upload. Original model/profile files
are never overwritten. Per-edge hole/contour offsets remain separate downstream
slicer settings; mesh preview does not simulate them or brim/support.

A completed slice stays immutable: discard/reselect to prepare another version.
At Slice start, browser fields lock to the server's chosen transform snapshot,
including another tab's choice. The original-source hash does not change; the
G-code artifact has its own hash. A per-receipt `source_id` changes even when the
same bytes/name are reselected, so an old slice lock/draft is not reused. Save and Start remain separate direct button
actions with existing policy/identity/READY checks and no automatic retries.
The user must still inspect the actual G-code result before printer actions.

## Coordinate contract

- Source STL coordinates are mm. Source3MF units/build transforms first flatten
  through the existing geometry-only importer, never imported presets/scripts.
- Source coordinates are quantized to Float32 before layout, matching the
  worker/Three source arrays for both ASCII and binary STL.
- Uniform scale first, then **extrinsic X → Y → Z** right-handed rotations
  (`Rz * Ry * Rx` on column vectors), about the **original bounds centre**.
- Recompute actual transformed **vertex** bounds, not rotated AABB corners.
  Translate so their XY centre is the requested X/Y, and minimum Z is zero.
  This seats the lowest point; it is not a face-to-bed picker, support generator,
  contact-area/adhesion test, topology repair or physical bed measurement.
- Current manual mode is deliberately restricted to a server machine profile
  with nominal centred140×140×140mm dimensions matching the editor grid. A
  different profile fails explicitly, rather than adapting a hidden origin.
- Nominal mesh bounds must fit XY±70 and Z≤140 (numerical tolerance1e−5mm).
  This is not nozzle/head/frame/clip clearance or an all-toolpaths bound. Layer
  quantization, compensation, brim/skirt/support can extend beyond mesh bounds.

**Start/purge paths do not move with the model.** The current draft02 fixed prime
is known to cross some footprints; this milestone does not modify it or promote
the separate offline draft03 skirt. Inspect both startup and actual toolpaths.
No collision-safe placement or hardware approval follows from this editor.

## API and implementation

Explicit POST `/api/slice` adds optional `transform` and `source_sha256`:

```json
{"confirm":true,"source_sha256":"<current 64-hex source hash>",
 "transform":{"scale":0.5,"rotate_x":90,"rotate_y":0,"rotate_z":0,"x":25,"y":30},
 "settings":{"xy_hole_compensation":0,"xy_contour_compensation":0}}
```

`transform:null`/omitted preserves automatic arrangement. A transform object
(including `{}` for explicit centred manual identity) requires the exact current
source hash. The browser also supplies `source_id`; if present it must match
this receipt/slot even for identical bytes. Unknown fields, strings, bools, nonfinite/out-of-range values and
stale source identity fail before starting a job. No arbitrary native flags,
paths/profiles, targets, negative/mirror scaling, Z offsets, per-axis scale,
multi-model editing or gizmos are exposed. Model drafts live per browser until
Slice; there is no shared editing mutation endpoint or automatic reslice.

`model-transform.js` computes the display matrix/bounds without modifying raw
vertices. `model-preview.js` publishes only a source-bound draft/error/lock event;
`app.js` attaches it only to explicit Slice. Drafts cannot silently apply to a
new source; after another tab slices, fields adopt the server snapshot and Slice
is disabled. Cached state observations reconcile the page and viewer together;
in-flight/pending/uncertain operations veto automatic reconciliation, so a
stale parent render cannot unlock another tab's slice or clear an uncertain
job warning. Invalid/stale drafts block Slice, not a guessed fallback. Camera
controls do not publish edits. Paused/unavailable preview cannot validate a
manual draft; turn manual mode off for independent automatic slicing.

`model_transform.py` validates/reads bounded binary or ASCII STL and writes
flat-normal binary STL. Same preview limits:32MiB,200k triangles,4096-character
lines,2M lines and finite source coordinates within±100000. Python tests cover
combined rotation against independent sequential operations; Node math is
checked against real vendored Three Euler/vertex operations. A source with
zero-area facets is not repaired; finite transformed vertices do not prove a
watertight or printable solid.

The transform stage runs in an isolated stdlib child through the existing
resource/process-group wrapper: at most512MiB virtual memory,30s wall time
(or smaller configured limits), CPU wall-time ceiling+1, workspace/log/file
quotas, capture failure propagation, cancellation/kill/drain/reap and scratch
cleanup. It runs before native help/slice. Mesh/profile/fit failure cannot
publish an artifact or initiate a printer connection. Resource bounds are not
an OS security sandbox. Source directories/executables/profiles remain trusted.

Manifest `model_transform` retains normalized intent (also on helper failure),
and `geometry_transform_limits` records the helper caps. Successful
capture event/metadata `geometry_transform` retain normalized transform, baked
STL size/hash, triangle count, transformed bounds, arrange/orient0 and an
explicit non-safety note. `slicing_inputs.model` remains the **original** source
hash;3MF `geometry_import` remains the intermediate unedited geometry hash.
Derived geometry and G-code can disclose private models: keep raw evidence,
local profiles, reports and outputs ignored. No raw capture is edited.

## Observed offline acceptance (not hardware)

Native Orca2.3.0, private draft02, unchanged original profiles. An initial
arrange0 probe confirmed both shifted STL and an internally generated minimal
3MF retained XY (captures under `captures/placement-probe/`:
`20261115T092854Z-7afa720e945d`, `20261115T092855Z-02c44a7e4aec`). Production
manual mode uses only a baked STL, never a supplied project archive in Orca.

Actual adapter trials under `captures/placement-native/`, generated20×10×5mm
cuboid unless noted:

| Capture | Requested transform | Actual nominal body XY bounds (mm) |
| --- | --- | --- |
| 20261115T094405Z-00cf90a27732 | X25/Y30 | X15.2..34.8, Y25.2..34.8 |
| 20261115T094406Z-76b849397ccb | scale0.5, X-rotation90°, X25/Y30 | X20.2..29.8, Y28.95..31.05 |
| 20261115T094406Z-7831c3aa69a8 | scale1.5, Z-rotation90°, X−30/Y20 | X−37.3..−22.7, Y5.2..34.8 |
| 20261115T094406Z-e3d15e9ff733 | supplied3MF, scale0.5, Y-rotation90°, X20/Y20 | Private derived geometry/output retained; slicing succeeded |

All four finalized with zero printer sessions, final E delta−1.3mm and resolved
nominal Z components≤7mm/s. These diagnostics do not model homing/offsets or
certify placement, firmware, support or material safety.

Actual ephemeral HTTP upload→typed Slice→native output trial:
`captures/placement-http/20261115T094821Z-2c26d4416922`, matching the third row's
body bounds. Source GET remained byte-identical, generated artifact/source
hashes stayed separate, Save was disabled/refused, and no printer client/session
was invoked. Temporary web workspace was project-local and cleaned. These are
native application observations, not independent Finder protocol evidence.

Automated checks include typed bounds/math/immutable source, actual baked input
and arrange0 inspected by fake CLI, before-native failure, stale source/API
binding, snapshot lock, draft/no-auto-Slice behavior, invalid-edit hiding and
real Three world matrices with mocked GPU. Existing quality/upload/status tests
remain. The composed page/editor event-bus test also covers receipt epochs,
remote snapshot locking and the uncertain-job reconciliation veto. Add
`node tests/test_model_transform.js` and `node tests/test_model_editor_integration.js`
to the documented suite.
New rendered-browser controls/WebGL/LAN and host Orca2.5 placement acceptance
remain user-run; agent ABI still cannot run2.5. No physical test/connection or
changed-profile approval occurred. Face picker, gizmos, multiple models and
nonuniform scale remain separate future work.
