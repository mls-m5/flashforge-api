# Input model preview before Slice

## Current scope

The page now has a separate **Model preview** between file receipt and Slice.
Drop the current `.stl` or supported geometry-only `.3mf` and inspect its solid
mesh **before slicing**. G-code preview remains below Slice for comparison.
The geometry viewer calls no printer transport or native Orca and initiates no
automatic Slice/Save/Start. The user accepted this initial preview; a separate
numeric editor now drafts scale/rotation/XY moves and commits only on explicit
Slice. See MODEL_TRANSFORMS.md for its coordinate/resource contract and native
placement evidence. Original geometry serving described below is unchanged. Existing configured status polling
is independent and may yield/reclaim its own observation session while a 3MF
preview conversion holds/releases the local slot.

Restart the backend when no local job is active and reload browsers. Drag to
orbit the camera, scroll/pinch to zoom, right-drag/two-finger drag to pan. Fit
camera and wireframe are available. Pause releases the model geometry/worker.
Camera dragging still only rotates/pans the camera. Numeric model scale,
rotation and XY controls now exist separately (MODEL_TRANSFORMS.md); face-to-bed
picking, mouse gizmos, multi-model editing and image/GX export remain future work.

In automatic-arrangement mode, displayed geometry is centered in XY and lowered
to the nominal plate **only for display**; Orca still arranges and may rotate it
differently. In manual mode, preview uses the typed layout that explicit Slice
bakes into a private derivative with arrange0. Original source bytes and imported
units/build transforms are not rewritten. STL units are assumed mm; 3MF units/transforms follow the existing
bounded importer. The nominal centered 140 mm grid is not measured clearance.
This view shows original geometry, not hole/contour compensation, brim, support
or material deposition. Use the separate G-code view to inspect slicing results.
A plausible mesh is not watertightness, winding, material or print-safety proof.

## Source identity and API

`/api/state` exposes `model`, `source_sha256` and a per-receipt `source_id`. The original source hash
survives Slice while `sha256` changes to the generated print artifact. The
model view keys only on the source identity/receipt/name, so it stays the original
mesh during/after slicing instead of interpreting G-code as a model.
Discard/source changes clear geometry and invalidate in-flight work; failure
clears old geometry and requires explicit Reload for the same failed source.
Cached state polling is serialized, with only one pending refresh retained.

GET `/api/model` requires the per-run **X-Finder-Token** from GET `/api/config`,
in addition to existing LAN authentication, peer/Host checks. This prevents
cross-site image/GET triggers from preparing a derivative. Its If-Match / ETag
is the **original source identity**, not a claim that a derived body's bytes
hash to the source archive hash. Busy/current-source/identity guards apply.
There is no browser path, command, executable or arbitrary geometry selection.

- STL: stream the unchanged original file from the current private slot.
- 3MF: use the same geometry-only importer as slicing, in a dedicated Python
  subprocess. Limits: 512 MiB address space, 15 s CPU, 20 s wall time, 64 MiB file size
  (the importer separately caps output at 200k triangles / approximately 10 MiB).
  No scripts/presets/material/start code or archive extraction. Cache the STL
  derivative in the current private slot, conservatively reserve its maximum
  size in workspace admission, reuse it on subsequent reads and remove it on
  discard. Unsupported components/extensions fail explicitly; export STL.
  Errors/cancellation/timeout kill/reap the process group, remove partial output
  and restore the previous local phase/busy flag. Foreground operations cannot
  overlap conversion. The model controller signals preparation to disable job
  controls immediately; after headers/abort the main page reconciles cached
  state (without clearing an existing uncertain-job warning). Failed preview does not rewrite source or create unknown
  printer outcomes; explicit Slice can still be attempted independently.
- The cache is derived data, not a raw capture edit or new print artifact.
  It persists only with the slot and counts against web storage. No capture,
  slicer log or printer session is created by model GET. Explicit manual Slice
  separately records derivative metadata (MODEL_TRANSFORMS.md). Source directories/local writers
  are trusted; source ETags are not an OS security sandbox/integrity monitor.

## Browser geometry and rendering

`model-worker.js` parses binary/ASCII STL off the main thread, checks finite
coordinates and bounds, computes flat normals and reports dimensions/zero-area
facets. The 3MF response is already a geometry-only binary STL, not ZIP/project
code interpreted in JavaScript. Worker limits: 32 MiB source, 200k triangles,
4096 characters/line,2M ASCII lines, absolute coordinate 100000 mm (a resource
limit, not travel clearance). Empty/unsupported/truncated/nonfinite/excessive
geometry fails visibly; no silently truncated model. Zero-area triangles are
reported, not a guessed topology repair; all-zero-area input fails.

`ToolpathView.setModel` reuses the locally vendored MIT Three.js scene/camera
controls, adds one normal-shaded double-sided Mesh, and supports wireframe.
The display-only translation never mutates the vertex array. The old toolpath
line batches and controls are unchanged. Both scenes render on demand, cap
pixel ratio2 and dispose replaced geometry/materials. Module/worker assets are
explicitly allowlisted and protected by the same auth/CSP policy. No CDN,
additional dependency/addon, printer storage fetch or remote upload.

`model-preview.js` uses only fixed config/state/model GETs, with source ETag,
AbortController, generation tickets, worker termination and 30 s browser deadline.
It does not modify shared model/project state from camera controls. Numeric
edits now publish only a source-bound local draft for explicit Slice.

## Checks and remaining work

Python HTTP tests cover raw STL before/after Slice, independent source hash,
token/identity/auth, current-slot cache creation/reuse/discard, unsupported 3MF
failure, process cancellation/reaping and no FinderClient/Orca/capture calls.
Node tests cover ASCII/binary mesh parsing, normals, bad/truncated/large values,
source/model controller identity across Slice and late-worker cancellation.
The real vendored Three math/geometry test (mocked GPU) verifies display-only
translation, mesh/wireframe, bounds and no source mutation. Run the existing
suite plus:

```sh
node tests/test_model_worker.js
node tests/test_model_preview_ui.js
```

An actual ephemeral loopback HTTP trial with the supplied 3MF received the model,
ran only the isolated geometry worker, served/cache-reused the 376984-byte STL
matching the earlier reviewed derivative, stayed `model_ready`/unsliced and
created no captures or printer/native-slicer calls. Its temporary workspace
was project-local and cleaned up. Private retained STL/derived fixture smoke
parses also succeeded; zero-area facets in existing inputs are reported.
These are not physical or rendered-browser/GPU acceptance. The user reports
the existing G-code view is useful and the initial model view works. The new
numeric editor still needs browser/host2.5 acceptance (MODEL_TRANSFORMS.md);
the agent has not rendered either view on a GPU.
The fixed-purge overlap remains separately queued in ROADMAP.md, not changed.
