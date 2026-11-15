# Geometry-only core-mesh 3MF import

## Use now

Restart the web backend when no Save/Slice is active and reload the page. Drop
`.3mf` just like STL, explicitly **Slice model offline**, then review/download,
confirm Save and separately confirm Start. A 3MF is never sent directly to the
printer. CLI `slice model.3mf` and `upload model.3mf --slice` use the same importer.
The file/name/quota/confirmation/firmware gates and default upload-only behavior
are unchanged. Orca still arranges the geometry and ensures it is on the bed;
this is not the future manual plate editor or G-code preview.

## Why a geometry derivative

Orca supports native 3MF, but a project can contain printer/process/filament
presets, start/end code, scripts or modifier settings. For this initial urgent
workflow **the original 3MF never reaches Orca**. `model_3mf.py` reads a bounded
core mesh subset and writes a temporary binary STL geometry derivative. Only
that STL and the existing server-owned JSON snapshots are supplied to Orca.
Layer height, filament, temperatures and templates therefore come from our
profiles/typed web overrides, not project metadata. Native direct-project
loading with trusted configuration precedence remains future work, not an
alternate enabled path. No automatic fallback/import of project settings.

Supported:

- One internal root model selected by `_rels/.rels`, core2015 mesh resources.
- Multiple mesh objects/build items flattened into a single geometry STL.
- Core units converted to mm, build affine transforms (rotation/scale/translation),
  mirrored winding corrected, printable=false items excluded.
- Zero-area facets are skipped and counted, not silently reported as valid
  surfaces. No repair of holes, topology or physical clearances is promised.

Not supported: component assemblies, external model references, required
extensions, advanced mesh geometry or preserving per-part modifier/material /
colour assignments, supports, project plates or arrangements. These either
fail when geometry cannot be interpreted or are explicitly not imported as
settings. Use STL export for unsupported geometry. The printed dimensions,
orientation/material and toolpath must still be reviewed, especially for
heat/load-bearing tools: successful slicing does not establish material fitness.

## Bounds and provenance

No archive extraction, host path selection, network requests or embedded code
execution. ZIP paths, duplicates, symlinks, encrypted/unsupported compression,
DTD/entities, invalid indices/nonfinite fields, singular transforms and expanded
triangle limits are rejected. Limits: input web model64MiB, archive256 entries /
64MiB declared uncompressed, XML16MiB,300k source vertices /200k source and
expanded triangles,256 build items. A bounded EOCD check precedes ZIP central
entry allocation; split/ZIP64 is unsupported. Geometry STL must also fit the
adapter model/output-workspace bounds. Work is in project-local private scratch,
cleaned on completion/failure; a failed derivative is never published or passed
to Orca. This bounded importer is not a hostile-native-code sandbox.

The capture retains the original model snapshot hash in `slicing_inputs.model`.
`geometry_import` event/metadata separately records derived STL size/hash,
triangle count, skipped zero-area count, transformed bounds/unit conversion and
`embedded_settings_loaded:false`. Existing profile/effective-setting hashes
remain separate. The source archive is never modified; geometry/reports/raw
captures remain private. No new printer commands/framing/timing are introduced.

## User tool: actual offline native trial

The supplied nozzle-replacement-tool project was inspected locally. It contains
one core mesh/build item and Prusa/Slic3r project settings. Native **Orca2.3.0**
via the normal bounded adapter accepted the geometry-only derivative:
`captures/3mf-import/20261115T080521Z-1bf3ef0465bd`.

- Geometry7538 triangles, two zero-area facets skipped; dimensions approximately
  41.18×69.18×19.90mm after build transform. Original project retained unchanged.
- Native generation succeeded:1161789-byte G-code; estimated41m2s (not measured).
- Generated configuration: layer0.18 / first0.27mm, nozzle220°C, filament1.75mm,
  Marlin emission, consistent with the unchanged private draft02, not imported
  project presets. Last E delta−1.3mm. All source profile hashes stayed unchanged.
- Capture finalized with **zero printer sessions**. No upload/Start or hardware
  action by the agent. Geometry generation is not collision/material approval.
- Host Orca2.5/browser acceptance remains user-run; agent2.5 is ABI-incompatible.

Generated-package tests cover transforms/units/reflection, preset exclusion,
malformed/external/unsupported inputs and quota bounds. Fake-Orca and ephemeral
loopback HTTP tests verify 3MF is model-only, cannot directly Save, gets server
profiles/overrides, and generates a separate downloadable print file. Existing
CLI/web tests remain standard-library only. G-code preview was paused for this
urgent milestone and is now implemented separately; see PREVIEW.md.
