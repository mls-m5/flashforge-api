# Multiple STL models on one plate

## Workflow and scope

The file picker/drop zone now accepts several STL files at once, or further STL
files after the first receipt **before Slice**. A two-or-more-model plate shows
all meshes in one 3D view. Select by list or a short click on a mesh (yellow
bounding box), then use independent XY centre, XYZ rotation and uniform-scale
fields. Camera drag still orbits/pans; no object-drag gizmo/face picker yet.
Remove selected model is explicit and revision-bound. Removing down to one
restores the existing single-model view; Discard removes the final file/plate.

Uploads are serial, not competing slot writes. On a failed/lost receipt the
batch stops; already received models stay listed. No automatic retry, discard,
Slice, export, Save or Start. Restart the backend when idle and hard-reload
browsers for the new state/API/modules. Existing print files and single3MF
retain their original workflow; multi-file3MF/mixed print-file plates are not
supported. The normal picker stays enabled for additional unsliced STL files
instead of unconditionally locking after the first file.

Initial positions form a simple fixed grid, **not** size-aware auto-arrangement;
large models may overlap or exceed bounds until you move/scale them. Existing
manual single-model draft is preserved when possible on entering plate mode.
Draft edits remain local to each browser; all tabs adopt the server's immutable
snapshot at Slice. Adding/removing changes receipt identity and invalidates
stale Slice/Save intents. After a Slice attempt, discard/reselect to prepare
another version; no published/saved/unknown artifact can be edited in place.

Explicit Slice combines the meshes into **one** G-code job, layer by layer.
The adapter bakes independent transforms into a private combined STL, forces
private process `print_sequence=by layer` and uses arrange0/orient0 with existing
validity/ensure-on-bed checks. No sequential whole-object printing, arbitrary
native flags, model-specific temperatures/processes or G-code rewriting.
Original source/profile files remain unchanged. Existing quality controls apply
to the whole plate. Native skirt/priming guard stays enabled in normal launchers.

GX uses the **exact baked combined mesh** retained with the successful plate
Slice, not only the first input or newly edited profiles. Its miniature therefore
shows all parts with their relative orientation/scale. Camera fitting translates
the assembly visually, not toolpaths. G-code body remains byte-identical; all
existing generated-output, exact identity, READY and no-retry/stop gates remain.
Creating/selecting the plate never initiates a printer connection.

## Bounds and implementation

- At most8 STL sources and64MiB aggregate originals; additional STL≤32MiB.
- Combined mesh≤200000 triangles; the existing finite-coordinate/parser bounds
  and centred140×140×140mm profile/mesh contract apply to every part.
- Require at least1mm separation between full-height XY axis-aligned boxes.
  This deliberately rejects some nonintersecting/interlocking shapes; it is not
  triangle collision detection, bead/head/clip clearance or print-safety proof.
  Brim/skirt/support/compensation can extend further; inspect actual output.
- Source parts are transformed with the same scale→extrinsic X/Y/Z→XY-centre /
  Z-on-bed math as the single-model editor. No topology union/repair is claimed.
- Child assembly runs through the existing resource/process-group wrapper with
  at most512MiB virtual memory /30s wall (or smaller configured limits), bounded
  logs/workspace and kill/drain/reap on failure/cancel. Additional16MiB web
  reservation covers retained compound geometry; no quota bypass or auto-prune.
- UI parses originals serially in bounded workers (combined200k limit), one
 45s generation deadline, abort/termination/tickets and no unchanged-error parse
  retry. Stable cached-state polls do not regenerate/upload mesh buffers.

State `models` contains opaque id/name/size/hash, never a browser-selectable host
path. POST `/api/file?name=...` appends only to an unsliced STL plate; failure
removes only its partial new file. GET `/api/model?model=ID` requires the usual
token and optional source If-Match, and streams only that current registered
source. No new access/CORS policy; LAN auth/Host/peer/CSP protection remains.
POST `/api/model-remove` requires confirm/source_id/model_id and cannot remove
the last part or mutate sliced plates. POST `/api/slice` accepts typed `plate`
entries `{id,transform}` with every current source exactly once and current
source_id. Unknown/duplicate/missing models, stale identities, transforms and
injected paths fail before starting. Only Slice's JSON cap rises to8192 bytes;
other JSON actions remain2048 bytes. A multi-model plate cannot silently fall
back to slicing just its first input if editor loading fails.

Capture `plate_assembly` event/metadata records all input hashes/transforms /
nominal bounds, combined SHA/size/count, arrange/orient0 and non-safety flags.
`plate_geometry` identifies the retained combined mesh; `slicing_inputs.model`
still identifies the primary source, not a falsely relabelled compound hash.
GX input hashes instead reference that actual compound mesh. Derived files,
models/images/reports and captures remain private/ignored. Discard removes the
slot, originals/compound/output, not historical captures. No raw capture edit.

## Checks and evidence

Python tests cover baking/identity/bounds/overlap, append/remove/stale IDs, partial
receipt preservation, source streaming, immutable Slice and GX using all models
with no printer calls. Node tests cover serial multi-file receipt, picker staying
available, independent editing/selection/removal, overlap errors/snapshot locks,
GET-only geometry and real Three multiple-mesh bounds/disposal with mocked GPU.

Native2.3/private03 trial: `captures/plate-native/20261115T173143Z-735740a875ad`
combined two generated20×20×5mm cubes, at X−25 and X25 (second scale0.75/Rz30°).
It produced122559-byte G-code with no priming issues, final E delta−1.3mm,
unchanged originals/profiles and no printer sessions. Separate GX capture
`20261115T173144Z-8ad707c2a959` contains137071-byte GX,24 combined triangles and
a locally viewed miniature showing both parts; exact G-code body equality.

An actual fresh ephemeral HTTP two-file→native Slice→GX trial also passed:
`captures/plate-http/20261115T173357Z-fe5f32f12c65` and
`20261115T173358Z-33725f97c786`, same sizes, zero printer/client calls, uploads/job
controls disabled and temporary workspace cleaned. This is offline application
acceptance, not independent protocol/physical printing or rendered-browser proof.
Browser/WebGL/LAN controls and host2.5 multi-model acceptance remain user-run.
The earlier user-confirmed GX printer display does not itself validate this new
plate workflow. No agent hardware action was authorized/performed.

Run the documented Python suite, `node tests/test_plate_ui.js`,
`node tests/test_plate_upload_ui.js` and the existing Node/trace checks.
