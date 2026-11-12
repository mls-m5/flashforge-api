# PrusaSlicer iteration 01 — OFFLINE EXPORT AND REVIEW ONLY

## Status and limitations

User-requested start/end **candidates**, derived from the supplied working FlashPrint GX and the diagnosed Prusa absolute-E mismatch. These snippets are **not a validated Finder profile or permission to print generated output**. The user will paste them into Prusa, export a new file, and return it for offline analysis before a hardware decision.

No firmware commands were sent. No STL was sliced here: PrusaSlicer is not installed in the coding environment. Its 2.9.7 generator version is known from the user's existing file; the host executable/headless setup still needs checking.

The candidates assume the same stock single-extruder Finder / V1.5 firmware as the working reference. Confirm the actual nozzle is 0.4 mm and that the material is the same PLA used for the known-working 220 °C reference. They are not universal scripts for other FlashForge models.

## Set these Prusa options before exporting

Use a **copy** of the current profile, not an overwrite of a known-good profile:

- G-code flavor: retain **Sailfish** for this comparison; do not switch to generic Marlin or insert unverified M82/M83 commands.
- Relative E distances: **disabled** (`use_relative_e_distances = 0`). Both prime and generated body must agree on absolute E.
- Nominal bed: **140 × 140 mm, centered origin** (polygon −70/−70, +70/−70, +70/+70, −70/+70); maximum height **140 mm**, not the supplied profile's 150 × 150 × 160. These are nominal dimensions, not a measured clearance certificate.
- Requested regular layer height **0.18 mm**, first layer **0.27 mm**. The old GX actually contains a 0.280 first model layer; leave that difference visible for review rather than silently claiming an explanation.
- First-layer and subsequent nozzle temperature **220 °C**, bed heating disabled / 0 °C.
- Set an explicit Z travel speed of **7 mm/s** (`travel_speed_z = 7`) to match the reference's G1 Z F420; do not leave it at 0, which allowed the 130 mm/s XY-travel setting to be used for Z in the supplied output.
- For this comparison, XY travel at most **80 mm/s**, matching the working reference's ordinary F4800 travel. This is not a general maximum-speed specification.
- Retain a reviewed retraction setting; the supplied profile used 2 mm and already generated a final body retract. The candidate end intentionally adds **no extra E move**.

Replace the printer profile's entire Custom G-code **Start** and **End** fields, not append to the old blocks. Also check whether the old scripts have been duplicated in filament-specific hooks; include the exported configuration so we can inspect all hooks. Do not blindly erase unrelated filament hooks.

Prefer a centered **20 × 20 × 5 mm** test box for the first eventual hardware trial. The current larger holder can also be sliced **offline** for comparison. The fixed purge path below must be reviewed against placement, skirt/brim, bed clips and real mechanical clearance; it is not safe for arbitrary placements. An empty, calibrated bed is a prerequisite for any later physical trial.

## Candidate Start G-code

The homing/heating/current sequence and purge path come from the working `test1.gx`. E is explicitly zeroed before priming, then again at the handoff to Prusa's zero-based absolute-E body. The fixed 220 temperature is the user's requested test value, not a universal material setting.

```gcode
; OFFLINE CANDIDATE - review exported file before printing
M140 S0 T0
M104 S220 T0
M104 S0 T1
M107
G90
G28
M132 X Y Z A B
G1 Z50.000 F420
G161 X Y F3300
M6 T0
M651
M907 X100 Y100 Z40 A80 B20
M108 T0
G92 E0
G1 X-25.00 Y-20.00 F4800
M106
G1 Z0.200 F420
G1 X-25.00 Y-20.00 F4800
G1 X55.00 Y-20.00 E11.6011 F1200
G1 X55.00 Y20.00 E17.4017
G92 E0
```

The 0.200 Z move is for the **purge**, not the first model layer. With absolute E, the purge feeds 11.6011 mm followed by 5.8006 mm, not an additional 17.4017 mm in the second move. The last G92 makes a subsequent Prusa `E-2` a 2 mm retract rather than 19.4017 mm.

**Deliberate unresolved difference:** the copied `M118 X... Y... Z... T0` and `;layer_count: 166` are not included. The comment is stale/job-specific; M118 parameter semantics have not been verified on this firmware. Some community Finder profiles omit M118, but that is not proof for this unit. We will not invent a new set of job bounds. Its necessity/parameter generation remains a hardware-validation blocker; omission is part of this offline experiment, not a guarantee of equivalent physical initialization.

## Matching candidate End G-code — replace the old one too

Fixing the start alone does not remove the old +363 mm end extrusion. Do **not** retain `G1 E778.4812`, the fixed `G1 Z30.100` or the old XY park.

```gcode
; OFFLINE CANDIDATE - Prusa owns the final body retraction
M107
M104 S0 T0
G162 Z F1800
G28 X Y
M132 X Y A B
M652
G91
M18
```

This retains the working reference's final homing/offset/shutdown suffix, with Z homing before XY homing. It removes the model-specific E/Z/XY pre-park. That changed transition still needs review: the homing path, real clearance and firmware behavior have not been physically tested with this candidate. Do not replace it with an unbounded relative Z lift or assume that every high/tall print can use it safely.

No automatic stop (`M26`) or network print-start (`M23`) is added by these snippets. They are file contents, not commands to send to the printer during analysis.

## Return files for review

Save under ignored `upload/`, for example:

- `iteration-01.gcode` (freshly sliced output, not the old file renamed);
- `iteration-01.ini` (Prusa's exported current configuration), or a 3MF project retaining settings/placement;
- the small STL if different from the already supplied model;
- exact Prusa build/installation method if different from the reported generator version.

We will inspect the complete custom-start → body and body → custom-end transitions, all active E/motion modes/resets, retraction deltas, first/model layer heights, Z feed requests, body placement/envelope, unexpected added commands and duplicate hooks. The mock validates transport, **not collision safety**.

The current uploader accepts GX, not a bare Prusa `.gcode`. GX packaging/thumbnail generation is not implemented yet. Renaming `.gcode` to `.gx` is not conversion. A small **known-working FlashPrint-generated GX** is the available reference-print route today, with physical supervision; this new Prusa candidate is still export-only until reviewed.

## CLI integration later

PrusaSlicer exposes a CLI, including loading settings and exporting G-code. A typical Linux-host command, **to verify with the installed binary's `--help`**, is:

```sh
prusa-slicer --load iteration-01.ini --export-gcode \
  --output iteration-01-cli.gcode model.stl
```

Executable naming differs for AppImage and Windows console builds. Configuration/project settings and overrides must be controlled explicitly. This is a proposed invocation, not a tested/installed integration in this repository, and it does not upload/start a print.

References: [Prusa CLI documentation](https://github.com/prusa3d/PrusaSlicer/wiki/Command-Line-Interface), [Prusa macro placeholders](https://help.prusa3d.com/article/list-of-placeholders_205643), [community Finder/Cura definition](https://github.com/ronoaldo/FlashforgeFinderIntegration/blob/master/plugins/FlashforgeFinderIntegration/printer/defs/finder.def.json). External Finder examples are hypothesis sources, not a substitute for the supplied V1.5 reference and a separately approved hardware trial.
