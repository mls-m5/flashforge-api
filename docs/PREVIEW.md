# Local toolpath preview — linear paths, not print approval

## Current milestone

The web page now has a modular read-only Three.js view of the **current server
artifact**. It loads automatically after successful Slice (STL or geometry-only
3MF), or after receiving an existing `.gcode`/`.g`/observed `.gx` file. It does
not fetch printer storage, discover devices, connect/claim control, execute
G-code or mutate a file/profile. Existing Save/Start/Cancel policies remain.

Restart the web backend when no Slice/Save is active and reload the browser.
Use the same launchers and LAN password as before. No npm install, CDN, online
font or external model service is involved. Three.js requires a browser with
WebGL2; if initialization/parsing fails the error is visible and file/slicer /
printer controls remain independent. Actual rendered-browser/GPU/second-device
acceptance is pending: tests here use Node and fresh loopback HTTP only.

## View controls

- Drag to orbit the **camera**, wheel/pinch to zoom, right-drag/two-finger drag
  to pan, **Fit camera** to reframe. No model transformations or plate editing.
- Green: inferred positive extrusion with resolved mode/origin. Blue: travel
  (hidden by default). Magenta: linear movement with unresolved extrusion.
- Height slider selects cumulative deposition heights, or All. These are
  sorted extrusion endpoint heights, **not guaranteed slicer layers**: a purge
  line/nonplanar move can add heights. A whole segment is hidden if either
  endpoint exceeds the selected height; no fake interpolated motion is inferred.
- **Assume absolute E when missing** is an explicit viewer-only assumption for
  older GX/G-code without M82. Off by default; otherwise extrusion can remain
  magenta. This neither modifies bytes nor establishes firmware modes.
- Pause automatic preview to release geometry/worker memory, or Reload preview
  to explicitly retry after an error. No automatic parse-retry loop for an
  unchanged failed artifact. Ordinary cached state polling is every2s.

The grid is a nominal centered140mm XY reference with XYZ axes, not measured
printer geometry. Coordinates are not rearranged/recentered in the model;
Fit changes only the camera. Known startup prime/end segments are included;
homing and unresolved origins are omitted and reported. Warnings and counts
remain visible, including when geometry appears plausible.

## Separation and batching

- `toolpath-worker.js`: independent bounded offline parser, no DOM/WebGL/network.
  The browser sends bytes with a transferred ArrayBuffer. It returns compact
  Float32 positions/segment heights and Uint8 extrusion/travel/unknown kinds.
- `toolpath-view.js`: reusable `ToolpathView`, accepting those arrays, no file
  paths or printer API. At most three LineSegments batches/draw calls for
  toolpaths, plus nominal grid/axes; not one Object3D per move. A segment-height
  attribute and shader uniform filter heights without rebuilding geometry.
  Geometry/materials are disposed when replaced/cleared. Rendering is on-demand
  (camera/control/resize changes), with pixel ratio capped2, not an idle loop.
- `preview.js`: controller, only GET cached `/api/state` and `/api/artifact`.
  Local app state events invalidate immediately; cached polling detects changes
  made by another browser. AbortController, a generation ticket, worker
  termination and30s load/parse deadline prevent stale results replacing a new
  file. Errors clear old geometry, not retain a misleading successful view.
- The artifact response has an ETag of the state SHA-256. Preview sends If-Match;
  changed identities fail412 before reading; busy/missing files remain409/404.
  This binds downloads to the selected server state, not remote printer contents
  or defense against an external writer mutating private trusted storage.
- Worker/module/vendor routes are explicitly allowlisted, same-Origin only,
  behind the same LAN authentication and peer/Host guards as all assets.
  CSP adds only `worker-src 'self'`; no blob/eval/CDN exception is required.

The parser and rendering representation can later support richer surfaces,
image capture and sequence playback; those are **not** in this milestone.
No arrangement, auto-orientation, face-to-bed, volume/thickness simulation,
material estimation, exact timeline or GX/PNG generation is provided. Orca's
existing arrangement still determines model placement. The observed GX BMP
format in GX_PREVIEW.md remains a separate future container task.

## Interpretation boundaries

Modeled: bounded G0/G1 linear endpoints, G20/G21, G90/G91, M82/M83, G92,
relative/absolute E deltas and a simple retract/restoration debt for line
classification. Missing spatial origins are not invented at zero. XYZ G92
breaks the frame/connecting path. G28/G161/G162/M132 invalidate origins;
their real paths are not drawn. G90/G91 changes that conflict with a known E
mode make E unresolved until an explicit mode or the labeled assumption.

Units default to **assumed mm** before an explicit unit command, with warning.
Unsupported arcs/coordinate/extrusion-mode commands or ambiguous syntax
invalidate affected modal state; arcs are not approximated as straight chords.
Unrecognized commands produce warnings and conservative invalidation. Some
known temperature/fan/status/custom codes are ignored as geometry inputs, not
simulated. No homing/offset/frame model, pressure/flow/volumetric extrusion,
firmware speed/acceleration, true material width, clipping/head clearance,
thermal state or physical motion guarantees. G-code comments are not code.
Missing warnings or a green line never proves printable/safe toolpaths.

Bounds: source1byte..8MiB; strict UTF-8 body,4096 chars/line,500k lines,
250k rendered segments and4096 distinct deposition heights. Numeric fields
are finite/bounded; resolved coordinates capped at±100000mm (a resource limit,
**not** printable clearance). Excess complexity fails explicitly without a
silently truncated preview. The reviewed xgcode1.0 offset at byte20 selects
its G-code body; no GX thumbnail/header generation or format generalization.
Inputs and converted geometry remain private in browser memory; no disk cache,
new capture/event, altered recording or external upload is created by preview.

## Dependency and checks

Three.js **r170 /0.170.0** is vendored under `webstatic/vendor/three/`, MIT
license/copyright retained. Exact upstream URLs, hashes and the single local
OrbitControls import rewrite are documented in its README and verified by a
Python integrity test. No upstream parser/viewer implementation was copied;
the project parser/controller/scene are separate code. Updating the dependency
requires intentional license/integrity/regression review.

```sh
python3 -m unittest discover -s tests -v
node tests/test_web_ui.js
node tests/test_passive_status_ui.js
node tests/test_active_status_ui.js
node tests/test_manual_ui.js
node tests/test_toolpath_worker.js
node tests/test_preview_ui.js
node tests/test_toolpath_view.js
```

Worker tests cover modes/E resets/retraction, unknown origins, inch conversion,
GX offsets, unsupported arcs/syntax, coordinate-frame breaks and input bounds.
Controller mocks check identity/cancellation/late-worker/error/no-retry behavior,
height/travel controls and strictly GET-only API use. Python HTTP tests check
ETag/If-Match, busy/discard, asset whitelist, auth on modules/worker/vendor and
no FinderClient invocation/new captures. An additional real vendored Three.js
geometry/math test (mocked WebGL/orbit host) checks batching, attributes, height
uniforms, camera and disposal. These are not rendered WebGL tests.

Offline parse smoke checks on retained private files found:
- Existing small-pan G-code:1075 extrusion/123 travel segments,26 deposition heights.
- User-tool native3MF output:35525 extrusion/1698 travel segments,111 heights.
- Provided GX:122663 unknown-extrusion/6257 travel segments by default (no M82);
  the absolute-E assumption is deliberately not silently applied.

These counts are parser observations, not independent printer protocol evidence.
No agent printer connection was made. Next acceptance is a user browser test of
camera/height controls on the native host output, including LAN/Basic-auth
module/worker loading, GPU/resource behavior and old-file invalidation. Volume
rendering, sequence playback and image export can follow after this foundation.
