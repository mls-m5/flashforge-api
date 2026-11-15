# XY hole and outer-contour compensation: next Slice only

The user reports holes printing about0.4mm too small in diameter (approximately
0.2mm excess material per side) and requests a web setting. This is a reported
fit error, not an independently measured universal Finder calibration.

## Use the web control

Restart the web backend when no upload/slice is active, using the usual launcher,
and reload both browsers to get the new backend/token/UI. In **Slice and review**:

- **XY hole compensation** initially0mm: off. Enter **0.2** to try enlarging
  an internal XY hole by approximately0.2mm per edge /0.4mm in diameter.
- Allowed range: finite numbers from−0.5 to+0.5mm per edge. Negative shrinks
  openings. The browser's spinner increments0.05mm; input is an absolute offset,
  not a percentage or a direct diameter change. Clear for server profile.
- **XY contour compensation** separately adjusts outer boundaries: initially0mm,
  finite−0.5..+0.5mm per edge, clear for profile. **−0.2mm reduces outer width /
  diameter by about0.4mm**; positive enlarges. Hole and outer settings are
  independent, not one uniform scale. Combining outer−0.2 with hole+0.2 can
  thin a wall by roughly0.4mm; inspect narrow walls before printing.
- Confirm Slice, then review/download. No reslice, upload or Start is automatic.
  Applied compensation is displayed with the output, including both independently
  configured hole and outer-contour values. An existing sliced/print file cannot be
  retroactively changed: discard/reselect and slice a new version.
- This affects internal XY contours/openings, not whole-model scale, Z error,
  every hole orientation, flow calibration or guaranteed dimensional accuracy.
  Thin walls/webs may shrink/disappear. Use a small test part with measured
  holes in the intended orientation/material/layer settings before trusting fits.
  First-layer squish/elephant foot and size-dependent errors may need separate
  investigation. A successful native slice is not a physical safety certificate.

The settings are Orca's existing **`xy_hole_compensation`** and
**`xy_contour_compensation`**. Only selected allowlisted fields in a validated
private process snapshot change. Original machine/process/filament files,
templates, temperature and retraction are untouched. Save/Start/Cancel, monitoring and LAN controls are unchanged.
No generated compensation candidate was uploaded/started or printer contacted.

## API, profile preservation and provenance

POST `/api/slice` accepts the setting only in its confirmed typed `settings`:

```json
{"confirm":true,"settings":{"xy_hole_compensation":0.2,"xy_contour_compensation":-0.2}}
```

Omitting the key or using null preserves the server process profile value;
**explicit0 means off**, overriding a nonzero profile. This preserves existing
CLI/library calls and no-override profile bytes/hashes. The UI defaults to an
explicit0, which can reserialize its private snapshot even when the source was
already0. No server profile file changes. Strings, booleans, NaN/infinity and
out-of-range values fail before native execution/printer access. Both offsets
use the same typed bounds and optional/profile behavior; arbitrary Orca options
remain forbidden as API inputs.

Normalized settings, actual process overrides, source/effective process hashes
and effective hole/outer-contour values are recorded in `slicer_settings` and
manifest metadata. These are applied to the artifact, not persistent global
printer calibration or a change to files uploaded without slicing.

## Native outer-contour and combined-offset trial (Orca 2.3.0)

Generated square ring, same unchanged draft02, second-layer Outer-wall nozzle
centreline extrema (not measured part surfaces). Captures under ignored
`captures/contour-quality/`, all finalized with zero printer sessions:

| Hole / contour offset | Capture | Hole XY extrema | Outer XY extrema |
| --- | --- | --- | --- |
| 0 / 0 | 20261115T072537Z-ff31ebea6336 | ±5.2 | ±9.8 |
| 0 / −0.2 | 20261115T072537Z-41fdfe0f3ab8 | ±5.2 | ±9.6 |
| 0 / +0.2 | 20261115T072538Z-405aaaed5696 | ±5.2 | ±10.0 |
| +0.2 / −0.2 | 20261115T072538Z-162a9ab17f6c | ±5.4 | ±9.6 |

This confirms negative contour shrinks the examined outer paths without
changing the opening unless separately selected. Source profile hashes and
final retract−1.3mm stayed unchanged. No output postprocessing/check disabling,
upload, Start or printer connection. Native2.5/physical fit and rendered-browser
acceptance remain pending. Typed snapshot/HTTP/Node tests additionally cover
positive/negative/zero/profile, invalid inputs and locked existing artifacts.

## Earlier native hole-only numerical evidence

Six actual **Orca2.3.0** runs via `slice_model`, unchanged private draft02,
created generated2mm-high rings with nominal10mm square/circular openings.
The circular fixture uses64 segments. Each run has a finalized private capture
under `captures/hole-quality/`, with **zero printer sessions**. Layer2 extruding
Outer-wall nozzle-centre paths around the opening were compared separately
from outer paths; these are path coordinates, not measured printed hole edges.

| Fixture | Per-edge offset | Capture | Hole X/Y centreline extrema |
| --- | --- | --- | --- |
| square | 0 | 20261114T223804Z-b504dbaaabe3 | ±5.200mm |
| square | +0.2 | 20261114T223805Z-95050fe63b96 | ±5.400mm |
| square | −0.2 | 20261114T223805Z-36603ae43c22 | ±5.000mm |
| circular | 0 | 20261114T223850Z-3d8220302b29 | ±5.194mm |
| circular | +0.2 | 20261114T223851Z-940b9c1e21ac | ±5.394mm |
| circular | −0.2 | 20261114T223851Z-ab296edb0fd8 | ±4.992mm |

Positive0.2 expands the examined opening paths by0.4mm across in both fixtures,
without changing outer centreline extrema (square±9.800, circle±9.788mm).
The circular negative case differs by about0.002mm per side from ideal offset,
consistent with polygon/resampling differences; do not claim exact analytic
circle dimensions or physical fits. All six outputs keep final E delta−1.3mm.
All original profile SHA-256 values stayed unchanged. Private geometry, review
reports and the offline helpers are retained under `.tmp/hole-quality/`,
`.tmp/circular-hole-quality/` and the capture directories, not distributed as
print-ready files. Raw captures are unchanged. No output postprocessing,
check disabling or hardware trial was used.

A separate actual ephemeral loopback HTTP receive → native2.3 Slice(+0.2) →
cached state → byte-exact artifact download also passed with upload/job controls
and monitoring disabled. Capture `20261114T224441Z-7f2eecfaa233` under
`web-data/hole-native-review/captures/` finalized with no printer sessions.
FinderClient construction was explicitly forbidden during this trial. This validates native HTTP plumbing,
not rendered-browser interaction or physical printing.

Fake-executable tests separately verify exact snapshot changes for positive,
negative, zero and profile values, preserving every other process key and
original profile bytes. HTTP/Node tests cover bounds, numeric types, no commands
on validation failure, explicit confirmation, per-artifact lock and effective
value display. Native2.5 compensation output on the user's host, rendered-browser
interaction and physical fit calibration remain acceptance checks; earlier
host2.5 output contains the default option but is not a nonzero compensation
trial. The agent's native2.5 runtime remains ABI-incompatible.
