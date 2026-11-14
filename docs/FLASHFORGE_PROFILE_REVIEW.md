# Official Finder download review

## Scope and sources

User-supplied page:
https://www.flashforge.com/blogs/download-material-profiles/finder-series

User specifically identified the Linux Orca ZIP, not only FlashPrint:
https://en.fss.flashforge.com/10000/software/a49b5937279bd409e3c9c4717df2644f.zip

The linked FlashPrint Linux DEB was also inspected as reference material:
https://en.fss.flashforge.com/10000/software/e02d016281d06012ea71a671d1e1fdb7.deb

These are externally published vendor artifacts, inspected locally offline;
they are not physical-printer measurements or a print-ready Orca preset.
No installer, AppImage, slicer or firmware from these downloads was executed.
No existing local profile was changed. No printer/proxy was contacted.

Downloads/extracted reference data are under ignored
`.tmp/flashforge-official-review/`, not redistributed in this repository.
Locally calculated SHA-256 values are integrity references, not vendor signatures.

## Exact Orca ZIP supplied by the user

- 101462732 bytes; SHA-256
  `163cab694f29aacfbe0d771da607533f5b01a22fc1c81da241a4bbb603800947`.
- Two ZIP entries: `OrcaSlicer_Linux_V1.8.1.AppImage` (103027904 bytes) and
  `__MACOSX/._OrcaSlicer_Linux_V1.8.1.AppImage` (1029 bytes).
- Thus this outer ZIP is a full application package, **not a loose JSON profile
  bundle**. The filename labels it V1.8.1; runtime version was not probed.
- The AppImage itself has SHA-256
  `055f22ec27f65e606c07100be5eba11f7123ff1c36da02565314602fc017b386`.
  It was copied out of the ZIP as data, never executed. Approved Debian
  `squashfs-tools` read its valid SquashFS v4 filesystem at byte offset 189632.
- The complete filesystem listing contains no Finder-named preset. All **2062
  profile JSON files** (3426512 bytes total) were read with `unsquashfs -cat`;
  case-insensitive `finder` occurs in none of those bytes. All 2062 records also
  decode as JSON without errors, and their decoded contents contain no Finder
  match (including Unicode-escaped strings). Concatenated JSON
  bytes SHA-256, in filesystem-listing order:
  `63b32859f19de71ad1015890598b5c0b92f12b6a16445880c1d159be9ab6c27e`.
- The actual bundled `resources/profiles/Flashforge.json` lists only
  **Flashforge Adventurer 5M** and **Flashforge Adventurer 5M Pro** machine
  models, with 0.4/0.6 nozzle variants. Manifest SHA-256:
  `9ea635b139d5f68308e4dda1f299022b01d0463739d509f9c2dbe45e76754439`.
  Its generic Flashforge filament presets
  are not a Finder machine definition and do not solve origin, dialect or
  start/end behavior. No Adventurer settings were transplanted to Finder.
- Conclusion scoped to this exact binary artifact: it supplies no named Finder
  or Finder 2 profile. Its placement on a Finder download page is not evidence
  of bundled Finder presets. Runtime/CLI/ABI compatibility of this older
  AppImage was not tested; do not replace the current executable merely to
  evade profile validity checks.

Read-only reproduction, after unzipping only the AppImage as data into a local
ignored scratch directory and verifying its hash:

```sh
unsquashfs -s -o 189632 PATH/OrcaSlicer_Linux_V1.8.1.AppImage
unsquashfs -ll -o 189632 PATH/OrcaSlicer_Linux_V1.8.1.AppImage
unsquashfs -cat -o 189632 PATH/OrcaSlicer_Linux_V1.8.1.AppImage \
  resources/profiles/Flashforge.json
```

Offset 189632 applies to the hash-pinned artifact above, not arbitrary
AppImages. The complete listings/read-only data remain under the ignored review
folder; no full vendor profiles have been added to runtime or Git.

Separately inspected public Orca-Flashforge source tree:
https://github.com/FlashForge/Orca-Flashforge/tree/c45cc8216c184574c36873314ae7caea67c7a1ad

Its complete recursive tree (7131 entries, not truncated) has no Finder-named
printer profiles; its `resources/profiles/Flashforge.json` has no Finder entry.
This scopes a negative finding to that commit, **not necessarily this older
binary package**. Its README identifies AGPLv3 and optional non-free networking
libraries; no source was copied into runtime code.

## FlashPrint 5.8.3 DEB: useful concrete Finder settings

- 26954800 bytes; SHA-256
  `eaf044b61403d073360fe97ed9dc1699d53e5cf26972f65033ed8632e69fe4fc`.
- AR members: `debian-binary`, `control.tar.xz`, `data.tar.xz`. Only selected
  bounded data files were read, without package installation or scripts.
- `usr/share/FlashPrint5/profile.dat`: 1651190 bytes; SHA-256
  `fc64577f075cb59dca0faccdd5a22d83a6709b435417b31c1ebb528d96436e44`.
- Read-only format observation: `fprofile` prefix, record count 801 at offset16,
  then 801 little-endian name-length/data-length pairs followed by UTF-8 names
  and payload bytes. Parsing consumes the entire file exactly (no trailing
  bytes). This describes this artifact, not a general FlashPrint format spec.
- Records 573–581 form `FlashForge Finder-0.4`, with separate PLA and TPU 95A
  (1.75 mm) Fast/Fine/Standard settings. Records 546–572 are separately named
  Finder 3 presets and were **not** substituted for the older Finder.
- The package also includes a firmware file named
  `firmware/FlashForge Finder/finder_1.5.20170419.bin`, matching the version/date
  reported by the user's printer. This strengthens relevance but is not proof
  that a profile explicitly named Finder (without 2) is validated for this
  particular physical Finder 2. Firmware was not extracted or executed.

### Selected PLA values (reference, not recommended print settings)

Source virtual paths: `FlashForge Finder-0.4/PLA-1.75/{Fast,Fine,Standard}`.
Units below follow the usual field interpretation; actual device/material
suitability still requires separate review.

| FlashPrint key | Fast | Fine | Standard |
| --- | --- | --- | --- |
| extruderTemp0 | 220 | 220 | 220 |
| platformTemp | 0 | 0 | 0 |
| layerHeight | 0.30 | 0.12 | 0.18 |
| firstLayerHeight | 0.30 | 0.20 | 0.27 |
| baseSpeed | 80 | 50 | 60 |
| travelSpeed | 100 | 70 | 80 |
| retractLen0 | 1.3 | 1.3 | 1.3 |
| retractInSpeed0 / retractOutSpeed0 | 30 / 30 | 30 / 30 | 30 / 30 |
| extrusionRatio / firstExtrusionRatio | 1.09 / 1.09 | 1.09 / 1.09 | 1.09 / 1.09 |
| shellCnt | 2 | 3 | 2 |
| fillDensity | 0.10 | 0.15 | 0.15 |

TPU 95A uses extruderTemp0=230, baseSpeed=20 and travelSpeed=70 across all three
quality variants; this is not a recommendation for the user's filament.

Generic fields such as chamberTemp=40 and extruderTemp1=220 also occur. They do
**not** prove heated-chamber or second-extruder hardware support. Machine/engine
capability logic is separate; do not blindly translate every INI field to Orca.
The inspected material/process records do not establish the required firmware
flavor, start/end templates, origin, homing clearance or safe machine limits.

## Licensing and next steps

The DEB's `usr/share/doc/flashprint5/copyright` contains placeholder license text
(`<Put the license of the package here indented by 4 spaces>`), not a clear
permission to redistribute the profiles. Full vendor payloads remain local;
this note records limited factual settings/provenance, not a shipped profile.

The exact AppImage inspection is complete: this download is not a missing
Finder preset bundle. The goal remains independent slicing followed by our own
byte-preserving transfer, not shipping or invoking FlashPrint.

Next decision: either explicitly investigate an Orca-compatible output dialect
as a new **offline** candidate, or evaluate another standalone slicer accepting
the current comparison flavor. The earlier Sailfish choice came from the user's
Prusa comparison, not a proven firmware requirement. Neither path may assume
that resolving an enum/profile error makes the resulting toolpaths safe. The
FlashPrint values above provide a real material/process baseline, not all
machine or code-generation semantics. Keep build envelope/origin, homing,
extrusion resets, machine commands and start/end transitions as separate review
items. Successful native slicing and complete generated-output review are still
required before any physical trial. Do not silently substitute Marlin for the
blocked Sailfish draft, import Finder 3/Adventurer settings, or disable checks.
