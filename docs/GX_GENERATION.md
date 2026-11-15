# Experimental GX generation with a CPU-rendered 3D miniature

## Workflow

After a successful supported Orca **Slice**, click **Create GX + 3D thumbnail ·
no upload/start**. This separate local operation renders the source mesh and
packages the **unchanged G-code bytes**. Download then returns `.gx`; a small
preview of the exact embedded bitmap appears on the page. The editable remote
name switches to the GX basename. Original model and G-code stay unchanged in
private storage. Once saved/unknown, conversion is refused; discard/reselect to
prepare a different version. No automatic conversion merely on Slice or GET.

Save/start are still explicit, separate from this export. The default-checked
start-after-upload option still means the later **Save + start** click requests
a print. GX packaging does not enable server upload/job permissions or bypass
`--allow-sliced-upload`: generated GX remains `sliced:true`. Renaming plain
G-code to GX remains refused. Only a successfully generated container permits
the GX extension. Existing uploaded GX is streamed unchanged, not repackaged.

**Experimental container, not physical firmware/display validation.** A pretty
image cannot make G-code safe or fix unsupported firmware commands. No printer,
proxy, hardware upload/start or remote read-back was used in development. The
actual Finder display, host2.5 metadata variants and browser/LAN image loading
still need user acceptance. The current source models/profiles remain private.

## Rendering, camera and image layout

`finderlab/gx.py` implements an original stdlib CPU triangle rasterizer: fixed
orthographic isometric view from +X/−Y/+Z, flat grayscale shading, two-sided
facets, per-pixel depth buffer and 2× supersampling. The 160×120 internal image
is averaged to **80×60**, black background. No GPU, browser screenshot, remote
render service, CDN, installed graphics package or new license dependency.
The bitmap is uncompressed24bit BI_RGB, BGR bottom-up, stride240,54-byte BMP
header,14454 total bytes,3780 pixels/metre matching the local samples.

The geometry is the source STL or the same supported geometry-only3MF flattening
used by Slice; project presets/scripts never load. Explicit manual scale/XYZ
rotation is applied using the editor's mathematical contract. Translation is
camera-fitted, so the miniature identifies the shape rather than its bed offset.
It does **not** include brim/skirt/support, compensation or physical material.
Automatic Orca arrangement may rotate/place the source differently; this is
explicitly recorded as `automatic_arrangement_not_reproduced:true`. It is not a
claim that source-mesh orientation equals exact sliced toolpaths. Your current
browser camera does not affect export. The separate G-code viewer still reads
the container's actual code offset and displays its body.

## GX header evidence and deliberately narrow encoding

New **local offline observation** compared two provided GX files, both reporting
`ffslicer1.30.0`/FlashForge Finder. User model Finder2; observed firmware in
prior recordings V1.5 20170419. FlashPrint application version unknown. Existing
known-working holder file `upload/test1.gx` and newly inspected
`upload/cube-20x20x5.gx` both have the following envelope. File/mesh/pixel content
is private and not committed. New sample inspection does not establish that the
newly generated container has been accepted by a physical device.

| Offset | Encoding used | Evidence/meaning |
| --- | --- | --- |
|0..11 |`xgcode 1.0\n\0` |Both local files |
|12 |u32LE0 |Observed constant; semantics unknown |
|16 |u32LE58 |BMP start |
|20 |u32LE14512 |G-code start |
|24 |u32LE14512 |Observed duplicate; separate semantics unknown |
|28 |u32LE seconds |External time interpretation; local values11155/410, not runtime measurements |
|32 |u32LE filament mm |External interpretation; local values13240/460 |
|36 |u32LE0 |Observed inactive second-extruder field; external interpretation |
|40 |u16LE11 |Observed constant/mode; full semantics unknown |
|42 |u16LE layer microns |Both local180 agree with0.18mm comments |
|44 |u16LE0 |Unknown observed constant |
|46 |u16LE shells |Both local2 agree with comments |
|48 |u16LE speed mm/s |Both local60 agree with base speed comments |
|50 |u16LE bed °C |Both local0 agree with comments |
|52 |u16LE T0 °C |Both local220 agree with comments |
|54 |u16LE0 |Inactive T1; both local0 |
|56 |u16LE1 |Unknown observed constant; **not** the0 in some external descriptions |
|58..14511 |Generated BMP |Layout checked by existing independent extractor |
|14512..EOF |Exact original code |Byte equality/SHA checked before publication |

We do not copy a prior print's job metadata, fabricate fields for a different
printer or interpret constants as universal flags. The generator deliberately
uses the matching observed single-extruder Finder envelope (`<12s7I9H`), with
unknown constants documented rather than generalized from Creator/Guider/etc.
The generated body's comments are **not** rewritten to impersonate FlashPrint.
FlashPrint's Slice Parameters window may parse comments differently; matching
its GUI metadata is not promised. No CRC/transport/protocol change is introduced.

External factual references (not Finder2 validation and no source code copied):
- [Slic3r issue4869](https://github.com/slic3r/Slic3r/issues/4869), cme-linux's
  GuiderII format notes and later comments on other models/extruder modes.
- [bkienzle format article](https://bkienzle.com/posts/converting-flashforge-file-format/),
  secondary discussion of GX offsets/BMP. Local observed values take precedence
  over reported constants that differ. These external implementations are not
  dependencies; renderer/header writer are project-original code.

## Metadata comes from the exact Slice, not mutable current settings

Successful slicing records optional `gx_metadata` from **effective private
process/filament snapshots** and the exact output: layer height→microns,
wall_loops→shells, sparse_infill_speed→nominal header speed, initial T0 temperature,
first unambiguous M140 bed target and Orca estimated normal-mode time / single
filament-used-mm comment. Length rounds upward to whole mm, speed/temperatures
round to integers; the header is an estimate/summary, not a speed-control command.
It does not describe all speeds, variable layers or temperature schedules.

Missing/duplicate/unsupported estimates, multiple filament values, inconsistent
initial T0 target or unrepresentable layer/shell values disable GX **without
failing Slice**. The page shows why. No generic print-time or filament-use guess.
Currently supported lines include `; estimated printing time (normal mode) =
22m 7s` and `; filament used [mm] = 1173.4` (or single total-filament-length-mm).
New syntax must be added with reviewed output/tests, not silently guessed.

POST `/api/gx` accepts only `confirm:true`, exact current `artifact_sha256` and
per-receipt `source_id`. It requires an unsaved successful model Slice with
stored metadata; browser cannot inject headers, model paths, camera, commands
or profiles. Original G-code/model snapshot hashes must match selected source
identities. Conversion retains generated-output provenance and existing access /
Origin/token/job locks. The selected artifact/hash/name changes only after a
complete export and finalized capture. Stale browser Save is rejected by its
artifact/receipt checks. On failure the original code remains selected, no GX
is published/started, and diagnostics appear as local errors.

GET `/api/gx-thumbnail?v=HASH` reads only the generated bitmap for that exact
current artifact. Stale hash412/missing404/busy409; no conversion side effect.
LAN Basic auth/peer/Host rules cover this route; CSP adds only `img-src 'self'`.
Discard/current-state transitions remove the browser's old image reference.

## Limits, private evidence and standalone tool

Export uses the existing bounded process-group wrapper in a fresh private
project-local `.tmp/gx-*` workspace: at most512MiB virtual memory,30s wall (or
smaller configured values), CPU ceiling+1, bounded stdout/stderr and workspace,
cancellation/kill/drain/reap. Mesh limits32MiB/200k facets (3MF uses its own
bounds first), coordinates≤100000, raster budget12M pixel/triangle tests. Empty/
degenerate/no-visible/unsupported/excessive input fails; no silent truncation.
The final **GX including header/image is at most8MiB**. Reserve8MiB plus capture
budget before web work; G-code snapshots/mesh/report are cleaned after completion.
A resource limit is not a native/OS sandbox, repair or clearance check.

New mode`gx` capture records original model/code snapshot hashes, typed metadata,
transform, bounded helper logs and `gx_result` candidate size/SHA, BMP/code SHA,
triangle count/bounds, render method and `firmware_validated:false`. The capture
must finalize before publishing the new file; complete means recorded, not
physical compatibility. The selected web artifact changes after export; old
slice/save captures/raw inputs are never modified. Full models, images, reports
and captures stay ignored/private; do not commit unreviewed source geometry.

For explicit offline exports independent of the page:

```sh
python3 tools/create_gx.py path/to/code.gcode --model path/to/model.stl \
  --metadata local-profiles/gx-header.json --output .tmp/review-only.gx
python3 tools/extract_gx_preview.py .tmp/review-only.gx --output .tmp/review-miniature.bmp
```

Create your own typed metadata JSON (values below are illustrative, not copied
or validated print estimates):

```json
{"print_seconds":125,"filament_mm":124,"layer_microns":180,
 "shells":2,"speed_mm_s":60,"bed_c":0,"nozzle_c":220}
```

Optional `--transform JSON_FILE` uses the editor's scale/rotate_x/y/z/x/y schema.
Default centres the source for its thumbnail; CLI does not claim mesh/code
matching. Always use the actual corresponding model and metadata. Output must
be a new `.gx`, never overwritten. JSON options≤64KiB. `captures/gx/` is the
default private recording location. No CLI upload/start or printer is invoked.

## Checks and actual application trial

Synthetic tests independently unpack headers, extract BMP, compare unchanged
body, grayscale rows/size, depth-buffer order invariance, repeatable translation-
invariant image/rotation change, resource/input errors, overwrite/identity/
recording failures and helper cleanup. HTTP tests cover source/artifact binding,
protected thumbnail bytes/hash, no connection during export, real-format remote
extension, no generated-output permission bypass and exact upload-only byte
transfer to a fresh dummy. Node tests cover explicit single-click export,
filename/hash changes, no automatic upload/start and stale image removal.

An actual ephemeral loopback HTTP trial used native Orca2.3.0/private03 with
guarded Slice of the supplied3MF at scale0.75/Rz37°/X20/Y15, then separate GX
export. Capture `captures/gx-native/20261115T134620Z-857b24dab220` retained the
761454-byte GX and extracted image privately, with original/code/profile hashes
unchanged, zero printer sessions and uploads/job controls disabled. Header
estimates1327s/1174mm came from that actual Slice. Source bitmap was decoded and
viewed locally; this is not physical printer-screen/browser acceptance.

Run `python3 -m unittest discover -s tests -v` and `node tests/test_gx_ui.js`
plus the existing Node checks and reviewed-trace integrity tool. Physical Finder
image/header acceptance and host2.5 metadata remain explicit limitations; do not
infer printability, clearance or permission for agent hardware actions.
