# Finder offline profile draft 01: copied, edited, blocked by Orca flavor validation

## Local artifacts and scope

At the user's request, a separate draft now exists under ignored
`local-profiles/finder-offline-01/`:

- `machine.json`, `process.json`, `filament.json`: resolved, edited standalone CLI presets;
- `slice.py`: convenience wrapper around **offline** `python3 -m finderlab slice`;
- `README.md`, `provenance.json`: warnings, source URLs/hashes, inheritance chain, normalization and complete setting changes;
- `originals/`: unchanged compiled preset snapshots, original upstream JSON and license.

The mounted Orca home was inspected read-only and was not modified. Its selected
machine was `MyMarlin 0.4 nozzle`; no saved custom machine/process/filament JSON
files existed in its user folders. No account settings, device registrations,
plugins or logs were copied. The pre-existing root `result.json` was left alone.
These local/private profile files are **not committed** as a supported preset.

The user subsequently approved a **separate** Marlin-emission offline experiment:
[draft 02](ORCA_FINDER_DRAFT_02.md) now generates native cube/holder review
artifacts. This original draft and its failed Sailfish trials remain unchanged;
new generation success is not physical-print approval.

## Provenance and inheritance

Both mounted `Custom.opc` and `OrcaFilamentLibrary.opc` were byte-identical to the
corresponding resource caches in the downloaded official Orca 2.5.0 AppImage.
They are binary preset caches, not ZIP exports. Original JSON sources were
retrieved from the official `v2.5.0` tag, following these complete chains:

- machine: `Custom/machine/fdm_machine_common` → `MyMarlin 0.4 nozzle`;
- process baseline (not a saved user selection): `Custom/process/fdm_process_common` → `fdm_process_marlin_common` → `0.20mm Standard @MyMarlin`;
- material baseline (not a saved user selection): `OrcaFilamentLibrary/filament/base/fdm_filament_common` → `fdm_filament_pla` → `Generic PLA @System`.

Parent fields were merged before detaching inheritance. The resulting files
were adapted to the installed 2.3.0 schema: unsupported newer fields were
removed, scalar/variant settings normalized, and explicit overrides recorded.
This is not a complete 2.5.0 GUI home copy or a tested GUI import bundle.
`from: system` identifies these fully resolved standalone configs to the 2.3.0
CLI's name-based compatibility gate; it does not mean they are official Finder
presets. No validity checks were disabled.

Attribution: [OrcaSlicer v2.5.0 profile resources](https://github.com/OrcaSlicer/OrcaSlicer/tree/v2.5.0/resources/profiles),
GNU AGPLv3, with unchanged source JSON and [LICENSE.txt](https://github.com/OrcaSlicer/OrcaSlicer/blob/v2.5.0/LICENSE.txt)
retained alongside the private derivative. No upstream implementation code was
copied into the application.

## Applied comparison settings

| Item | Draft value / qualification |
| --- | --- |
| Nominal build space | 140 × 140 × 140 mm; centered X/Y −70 to +70, not a physical clearance certificate |
| Flavor | Sailfish, carried over from the user's Prusa comparison configuration; **currently rejected by Orca** |
| Extrusion | Absolute E, with explicit prime/body resets in the offline start candidate |
| Nozzle/material | **Assumed**, not physically confirmed: 0.4 mm, 1.75 mm Generic PLA |
| Layer heights | User-requested 0.18 mm / 0.27 mm first layer |
| Nozzle temperature | User-requested 220 °C, first and subsequent layers |
| Bed temperatures | All configured plate/bed temperature values set to 0 |
| Travel | XY 80 mm/s, explicit Z 7 mm/s; comparison values, not general manufacturer limits |
| Retraction | Previous comparison's 2 mm at 40 mm/s; ownership/end transition still needs review |
| Other controls | Single extruder, no prime tower, arcs, object-exclusion commands or additional/exhaust fan commands; no explicit acceleration/firmware-limit emission |

The original generic Marlin start contains `M83`, bed heating and an X205 purge
move, incompatible with simply assuming the centered Finder comparison space.
It was replaced, together with its generic exit script, by the **unvalidated**
start/end candidate from [PRUSA_ITERATION_01.md](PRUSA_ITERATION_01.md).
Per-layer E resets and extra filament hooks were removed so extrusion resets
have explicit ownership for later generated-body review. No job-specific
absolute end E/Z/XY park was copied. The fixed purge path, omission of M118,
final body retraction and homing clearance remain unresolved. Other retained
generic settings (flow/cooling/infill, estimates and clearances) are not Finder
measurements. Do not print this draft.

## Native offline trials and decisive blocker

A generated 20 × 20 × 5 mm review cube was supplied only to the offline `slice`
command. No user model was uploaded and no printer client was invoked. The
local JSONs pass the adapter's structural profile checks, but actual native
slicing has **not succeeded**:

1. `20261114T091222Z-53559609ef80`: 2.3.0 CLI rejects process compatibility when a standalone `from: user` machine has empty inheritance.
2. `20261114T091308Z-2216cf6d8b75`: empty compatibility lists also fail that CLI gate.
3. `20261114T091406Z-47664b67deca`: explicit standalone `from: system` and matching named compatibility resolve that gate. The next validation error is **`gcode_flavor: invalid value sailfish`**, native exit 238 (reported internal error −18).

All are mode `slice`, with no printer sessions or generated G-code. No M23/M26,
physical printer, transparent proxy or existing loopback listener was used.

**Correction to earlier guidance:** an internal Sailfish enum is not evidence
that Orca accepts it as a configured flavor. Installed Orca 2.3.0 rejects this
value. The [2.5.0 PrintConfig source](https://github.com/OrcaSlicer/OrcaSlicer/blob/v2.5.0/src/libslic3r/PrintConfig.cpp)
also comments Sailfish out of its accepted flavor list; that is external source
inspection, not a native 2.5.0 trial here. Do not blindly advise selecting
Sailfish in Orca's UI.

This does **not** independently prove that Finder firmware requires Sailfish or
that an appropriately reviewed Marlin-emitted subset cannot work. The earlier
Sailfish choice came from the supplied Prusa file, not a full firmware dialect
specification. Switching flavor requires a separate offline compatibility
experiment and complete output/start/body/end review, not merely renaming the
option or using `--no-check`.

## Later invocation and next decision

The local runner is available:

```sh
python3 local-profiles/finder-offline-01/slice.py MODEL.stl
```

**With the current profile it reproduces the blocker; it is not a successful
slicing example.** It only wraps `finderlab slice`, accepts optional `--output`
and `--orca`, and does not expose upload/start actions. All outputs/logs would
remain local. Profiles are edited copies, not a hardware approval.

Next decision: retain Sailfish and investigate a slicer that supports this
comparison configuration (for example the user's Prusa workflow), or explicitly
investigate Orca's Marlin output as a separate **offline** Finder-compatibility
candidate. No silent flavor substitution, hardware trial or automatic print is
authorized by this draft.
