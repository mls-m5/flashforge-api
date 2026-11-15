# Native skirt candidate 03 — offline review, not the tested startup

## Current default selection (user-requested)

After the offline comparisons/guard implementation, the user explicitly asked
to replace the fixed prime with native skirt all the time. All standard offline,
owned-dummy, proxy and LAN web launchers now select this03 profile and always
pass `--check-priming`; missing03 fails rather than falling back to02. The
isolated `start_skirt_test.sh` retains a separate workspace/target restriction,
not a different profile. Original profile sets and raw captures are unchanged.
Restart/re-slice; existing G-code/printer files keep their original contents.
No physical trial/agent hardware action or general print-safety approval follows
from this software-default decision. Historical evidence/limitations below remain.

## Why a separate profile

The user observed that draft02's fixed holder-derived purge line can cross
larger prints. The original physically startup-tested draft02 is preserved
unchanged. A separate private `local-profiles/finder-offline-03/` now replaces
the fixed purge with native Orca **skirt**, generated around the arranged
footprint. This changes the startup path and priming strategy: the earlier
collision-free draft02 trial does not validate draft03 physical behavior.
No printer/proxy connection, upload, Start or hardware motion was performed.

Source lineage/license from the private draft02 derivatives is retained in
`originals/`, `base-provenance.json`, `draft02-provenance.json` and the new
`experiment-03-provenance.json`. No private profiles/model bytes are in Git.
These are CLI profiles for local experiments, not a shipped supported preset.

## Exact changes

- Remove the fixed G1 prime at X−25..55/Y−20..20, E11.6011/E17.4017 and its
  Z0.2 descent. No postprocessing of generated output and no disabled checks.
- Keep existing G28/M132/Z50/G161 and heating/current sequence. After it,
  stage at **X0/Y0** at the existing raised Z, with G92 E0 and no extrusion.
  The existing slow layer-change hook then sets first-layer Z0.27 before
  native first-layer paths. This is an explicit changed startup, **not yet
  physically verified**. Head clearance/homing/origin are not inferred from
  endpoint bounds, and the bed must be clear before any later approved trial.
- Set native `skirt_loops=1`, `skirt_height=1`, `skirt_distance=3`,
  `min_skirt_length=10`, **`skirt_speed=10` mm/s**. Orca can generate multiple
  loops to meet its minimum priming length. No model-specific absolute E is
  copied. The initial body retract/unretract remains slicer-owned1.3 mm.
- Skirt stays enabled **even with brim** in this candidate. Native generation
  placed it outside the brim in the examined cases. This uses extra material
  but keeps a distinct priming phase; it does not assume an arbitrarily tiny
  brim guarantees enough priming. Brim and quality options still use the GUI.
- End template, layer-change slow-Z hook, temperatures, extrusion mode/reset
  ownership and retraction settings are unchanged from draft02. No extra
  final retract or E-only purge is added to the end.

## Native offline trial evidence (Orca 2.3.0)

Initial tests confirmed native skirt placement but exposed the default skirt
speed50 mm/s. Explicit10 mm/s was then set and all four cases regenerated.
Final reviewed captures under `captures/finder03/`:

| Input | Outer brim | Capture | Full declared XY extrema |
| --- | --- | --- | --- |
| generated20×20×5 cube | off | 20261114T203332Z-4b80761c3814 | approximately±13.663 / ±13.663 |
| same cube | 5 mm | 20261114T203332Z-6441bce76d43 | approximately±18.18 / ±18.18 |
| supplied holder | off | 20261114T203333Z-e5ed00330c9e | approximately±53.221 / ±18.221 |
| supplied holder | 5 mm | 20261114T203339Z-c7a13efb01ad | approximately±57.742 / ±22.742 |

Actual generated first extrusion feature is `Skirt`, followed by Brim when
selected, then model paths. The cube with brim's skirt surrounds the expanded
footprint rather than crossing its middle. First-layer height remains0.27.
No fixed X55 prime or E17.4017 prime remains in custom startup. Final E delta
remains−1.3 mm; declared linear endpoints in these cases stay within the
nominal box, and resolved nominal Z components remain at most7 mm/s.
This is numerical/command-order observation, not measured travel/adhesion.

A generated136×136×5 boundary case was rejected by Orca with exit206 (capture
`20261114T203359Z-5a0bc5d68c4e`), with no published G-code. Do not disable
placement checks to make a near-full-bed model fit. This one rejection does
not prove every edge/shape is checked correctly. Always inspect generated
footprint, especially with large brim/skirt, and retain physical margins.

All these trial captures finalized without printer sessions. The four earlier
speed-default tests are retained separately under the same private capture
root. Original draft02 source hashes were recorded before copying and not
modified. Native2.5 on the user's host and rendered GUI need a separate retry;
2.3 behavior is not silently generalized to a new build.

## Updated exact-tool/manual-placement review and edge guard

See [PRIMING_REVIEW.md](PRIMING_REVIEW.md) for new native2.3 comparisons on the
supplied tool, including manual scale/rotation/translation and optional brim.
The fixed02 prime reproduces21 first-layer XY segment intersections;03 gives
Skirt first, no startup XY deposition and no skirt/object/brim intersections.
These refer to first-layer paths, not the full upper-model projection.

**New counterexample:** an unguarded manual edge placement produced skirt X72.105
with native exit0 although the mesh fit±70. The earlier136mm exit206 observation
is not a universal edge guarantee. The test launcher now automatically adds
`--check-priming`: a bounded diagnostic helper rejects missing/overlapping skirt
or first-layer extrusion beyond a conservative nominal±69mm margin before
artifact publication. Native-generated G-code is not rewritten to fit. This
check is not physical/swept-volume/firmware safety approval; the user later
explicitly selected03 for normal/proxy presets, with this guard always enabled.

## Short offline test script

Stop only the old web page when no local save/slice is active; do not interrupt
a printer/proxy merely to try this. Then:

```sh
./tools/start_skirt_test.sh
```

Open the printed URL, choose the generated cube first, explicitly Slice and
download for review. This selects the private draft03 files instead of draft02;
printer upload/job controls remain disabled. Optional
`./tools/start_skirt_test.sh --dummy-upload-test` enables virtual Save/Start/
Cancel **only to an owned fresh dummy**, not hardware. The launcher refuses
`--proxy-port` with this new startup experiment. Existing normal/proxy launchers
now select the same guarded03 at the user's explicit request; this is no
longer an opt-in-only profile choice, but not new physical startup evidence. Existing sliced files are not changed—reslice
before comparing.

There is no claim of physical approval, perfect priming volume, nozzle/head
swept-volume simulation or firmware safety. If the first line is underextruded,
minimum skirt length/material calibration may need a separately measured
adjustment. Brim-only priming remains a future option after validating first
extrusion order/volume and E transitions. Do not blindly delete both prime and
skirt. Next: review host2.5 output and resolve any fit/transition differences; physical
startup acceptance still requires user supervision, not an agent hardware action.
