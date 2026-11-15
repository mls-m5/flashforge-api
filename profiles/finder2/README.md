# Finder 2 / 0.4 mm / PLA — project profile

These three self-contained source JSON profiles are the project's current
user-selected **draft03 native-skirt** configuration. They are now distributed
with Git and the default Compose slicer image, following the user's explicit
request that deployment require no untracked settings except network/credentials.
They are byte-for-byte copies of the existing local draft03, **not a new tuning
or startup change**. Historical private drafts and raw recordings remain untouched.
Native launchers use this directory too; edit these tracked files for deliberate
future configuration changes, never a hidden ignored copy.

## License and source

Copyright OrcaSlicer contributors for the upstream profile resources;
Finder adaptations copyright2026 Mattias Lasersköld and project contributors.
The profile JSON derivatives and included upstream JSON source snapshots are
released under **GNU AGPL version3**; see `LICENSE.txt` (unchanged upstream text).
No warranty; not an official OrcaSlicer/FlashForge-supported Finder preset.
This directory has its own upstream-derived license, separate from the project's
GPLv3 Python code and MIT Three.js assets. Retain notices/source when sharing.

Upstream: https://github.com/OrcaSlicer/OrcaSlicer/tree/v2.5.0/resources/profiles
The eight original public JSON sources are in `upstream/resources/profiles/`,
with their original names/paths. `provenance.json` records pinned source URLs /
hashes, distributed profile hashes, review and modification dates. The original
compiled OPC caches, host settings, private raw logs/models and full local
experiment manifests are intentionally not redistributed or required at runtime.

## Modification lineage and effective settings

Modified2026-11-14: flattened the Custom MyMarlin0.4 and Generic PLA@System chains
into standalone CLI-compatible profiles, resolved2.5 multi-extruder metadata for
native2.3, removed unsupported/unused keys and host post-process scripts. Changed
names/compatibility, centered140×140×140mm envelope, absolute extrusion/reset
ownership, Finder startup/end templates, zero bed targets and220°C PLA. Set
0.18mm layers/0.27 first layer, line widths/speeds,1.75mm filament, flow1.09,
retraction1.3mm/30mm/s, no wipe/Z-hop and explicit separate layer Z step F420.
Removed copied job-specific end extrusion/parking; slicer owns final retract.
Changed fixed02 prime to03 native skirt: loops1/height1/distance3/min length10 /
speed10mm/s, startup stages XY0/0 at raised Z with no fixed extrusion. Kept
start/end/motion caveats and explicit profile warning comments.

Packaged2026-11-15: copied the final03 runtime bytes unchanged into tracked source,
added public-source/license attribution and deployment defaults. No temperatures,
start/end commands, retraction, skirt or geometry settings changed in packaging.
`filament_id=OFDSrzZ8` is the upstream generic PLA identifier, not a printer serial.
Manual review found no IP/MAC/serial/login/password/host file paths/model geometry
in these3 runtime JSONs or the public upstream JSONs.

## Use and evidence boundaries

Standard launchers/container always select `--check-priming`: do not disable the
guard or fall back to the old fixed02 purge. Raw CLI users must pass it explicitly.
No inherited GUI presets, external scripts or saved host configuration are needed.
Profile availability/successful slicing is not general firmware/head/clip/material
safety certification. No new agent hardware authorization follows from packaging.

Native2.3 offline skirt/guard/plate evidence and the out-of-bed edge counterexample
are in `docs/ORCA_FINDER_DRAFT_03.md` and `docs/PRIMING_REVIEW.md`. User-host2.5
multi-model Slice succeeded (capture20261115T180930Z-91f12d5e57e8); earlier physical
startup evidence was scoped to02, and user-reported GX screen-image acceptance
is not clearance validation. See `docs/PROTOCOL.md` and `docs/PLATE.md`. Actual
Docker/Podman image/runtime/browser acceptance still needs the deployment host.

Slice/GX are offline explicit actions. Default Compose owns a fresh dummy;
network/capability configuration is deliberately separate. No printer address,
credential, automatic print, model or private recording is bundled here.
