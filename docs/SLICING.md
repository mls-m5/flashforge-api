# OrcaSlicer CLI integration

## Status and boundaries

Implemented: `slice MODEL.stl` for offline export, and `upload MODEL.stl --slice` for sequential STL → Orca → plain G-code → the existing uploader. The async adapter is `finderlab/slicer.py::slice_model`; it does not import or invoke the printer client. The combined CLI does not open a printer connection until slicing has succeeded. Upload-only remains the default; the existing explicit `--start` still means save confirmation → READY check → start. There is no automatic stop or retry.

**Native offline generation now observed:** the separately user-authorized Marlin-emission [draft 02](ORCA_FINDER_DRAFT_02.md) slices a generated cube and the supplied holder with Orca 2.3.0. It is an experimental candidate, **not a validated Finder 2 profile**, physical plain-G-code trial or safe-toolpath certificate. Official 2.3.0/2.5.0 AppImages are downloaded/extracted locally. After approved runtime installation, native 2.3.0 help/capability probing succeeds, including under the adapter limits; 2.5.0 remains incompatible with this Debian 12 runtime. See [ORCA_INSTALL.md](ORCA_INSTALL.md) for paths, provenance, probe capture and host instructions. Automated tests use an independent fake executable plus fresh ephemeral dummy printers; they test orchestration/limits, not geometry or Orca compatibility. Earlier native work established help only; draft 02 now adds actual JSON loading/geometry generation. No physical trial of this generated output was performed. Native success does not establish firmware compatibility, homing/clip clearance or material calibration.

A user-requested local Finder draft has since been copied/edited, but its native offline trial is blocked by Orca rejecting `gcode_flavor=sailfish`. See [ORCA_FINDER_DRAFT_01.md](ORCA_FINDER_DRAFT_01.md) for the private artifact paths, source attribution, exact changes, failed trial captures and the next dialect decision. The earlier internal Sailfish enum observation was not evidence of an accepted Orca profile option.

The CLI/library is also used by the new [standalone local page](WEB.md). The page accepts an STL into a bounded local slot, requires an explicit offline Slice, offers output download/review, and requires a separate confirmed Save. Generated-output saving is server-disabled by default, independently of ordinary GX upload. Orca executable/profiles remain trusted server configuration, not HTTP parameters. The user request's “sdl” is interpreted as **STL**. Core mesh 3MF is now accepted through a bounded **geometry-only STL derivative**;
embedded project settings never reach Orca. See [3MF.md](3MF.md) for supported
transforms/units, rejected assemblies/extensions, provenance and the actual
user-tool native trial. OBJ/SDL inputs remain unsupported. STL coordinates are interpreted as millimetres: no automatic unit conversion, scaling, repair or auto-orientation. Orca is asked to arrange the object and ensure it is on the bed, using the supplied machine profile.

## Optional typed manual layout

The web editor/library now accepts a separate optional `transform` argument:
uniform scale, XYZ degrees and XY centre. Explicit Slice bakes a private STL,
then uses arrange0/orient0/ensure-on-bed to retain placement. Null/omitted keeps
the automatic contract above; the standalone CLI exposes no new flags. Manual
mode requires a matching nominal centred140mm machine, validates finite typed
parameters/mesh fit and source binding at the web API, and never changes original
profiles/model or a completed artifact. A bounded stdlib child records normalized
transform/baked hash/bounds before native help/slice. See MODEL_TRANSFORMS.md for
coordinate conventions, resource limits, native2.3/HTTP evidence and remaining
host2.5/browser/physical acceptance. Startup/purge is NOT relocated; mesh fit is
not head/clip/brim/support/compensation or firmware validation.

The user's official Finder download page is now under a separate read-only
review: [FLASHFORGE_PROFILE_REVIEW.md](FLASHFORGE_PROFILE_REVIEW.md). The exact
Linux Orca ZIP contains an AppImage labelled V1.8.1, not loose JSON presets.
Read-only inspection of its actual embedded filesystem found no Finder in all
2062 bundled profile JSON files; its Flashforge machines are Adventurer 5M/5M
Pro, not Finder. The linked FlashPrint 5.8.3 DEB contains concrete older Finder
material/process values, kept as local reference, not a redistributed or
converted Orca profile. This did not supply a Finder profile. The user subsequently authorized a separate
Marlin-emission offline experiment: draft 02 now generates geometry, while the
original Sailfish draft is unchanged and still rejected. See its separate
[trial report](ORCA_FINDER_DRAFT_02.md) before interpreting that progress.

## Install and prepare profiles on the host

1. Install a trusted OrcaSlicer build separately. On Linux use its CLI-capable executable (or a trusted launcher). Set `--orca /absolute/path/to/orca-slicer` if it is not on PATH. Discovery tries `orca-slicer`, then `OrcaSlicer`. The adapter currently requires POSIX process/resource limits; Linux is the development platform. Windows execution is not supported by this adapter yet.
2. Check that build's `--help`. The adapter runs and records a bounded help probe before every job and refuses missing required flags instead of guessing a different CLI. Some packages may need GUI/runtime libraries or a working AppImage/FUSE setup even for CLI execution; those are host installation issues, not automatically installed dependencies.
3. Supply **three trusted, fully resolved/self-contained Orca JSON profiles**, with `type` set to `machine`, `process`, and `filament`. Keep them under ignored `local-profiles/`. Ordinary GUI exports may be *deltas* containing `inherits`; these are deliberately rejected because the isolated datadir has no implicit user presets. Resolve/copy all ancestor settings into a separate derivative first. **Deleting `inherits` without merging its settings is not flattening.** Do not overwrite your originals. The adapter does not currently flatten presets or import Prusa INI files.
4. Review the effective settings and generated output offline before any physical use. No reviewed Finder 2 Orca profile ships with this change. An Adventurer/Finder 3/Bambu profile is not a substitute. The [Prusa investigation](SLICING_ANALYSIS.md) and [offline candidate](PRUSA_ITERATION_01.md) identify existing E-state, origin/envelope and Z-speed risks; Prusa macro syntax must not simply be pasted into Orca.

To prevent critical settings silently being omitted, each profile must explicitly include at least:

- machine: `gcode_flavor`, `printable_area`, `printable_height`, `use_relative_e_distances`, `machine_start_gcode`, `machine_end_gcode`;
- process: `layer_height`, `initial_layer_print_height`, `travel_speed`, `travel_speed_z`;
- filament: `nozzle_temperature`, `nozzle_temperature_initial_layer`.

Presence checks are **not** a semantic or safety certificate. Other settings must also be resolved correctly. Inspect Orca's warnings/substitutions and the complete start/body/end transitions. Profiles with host `post_process` scripts are rejected; embedded printer G-code templates remain profile contents for offline generation, not host commands. No scripts, safety limits or temperature/bed defaults are synthesized for Finder 2.

## Web quality overrides

The web Slice form adds a narrow typed allowlist for layer height, brim and
independent per-edge XY hole/outer-contour compensation; see [WEB.md](WEB.md). These values change only a validated private process JSON
snapshot before help/slice, with original/effective hashes and applied settings
recorded. No arbitrary JSON fields, CLI flags, templates, temperatures, machine
or filament settings are accepted. Omitted/profile selections preserve original
bytes. Hole values are finite−0.5..+0.5mm (positive expands openings); null/omitted
preserves the profile, explicit0 disables its compensation. The UI starts at0.
`xy_hole_compensation` expands openings for positive values;
`xy_contour_compensation` shrinks outer dimensions for negative values. Each is
independently optional with the same bounds/profile/zero behavior; both actual
values are captured/displayed. Only selected private process fields change. This does not fix every hole orientation
or ensure a fit; inspect thin walls and calibrate. See HOLE_COMPENSATION.md for
six native2.3 square/circular ring comparisons with unchanged outer bounds and
original profiles, no printer sessions, and pending host2.5/physical checks.
First-layer height, brim gap and retraction remain as configured by the server. The standalone CLI is unchanged and supplies no quality overrides by
default; the adapter's optional `settings` argument is independently validated.
Native2.3 cube trial verifies actual Brim paths/0.12mm layers with5mm outer brim,
not physical adhesion performance or every model's fit/clearance.

## Opt-in native-skirt candidate guard

`--check-priming` / `SliceConfig.check_priming=True` now runs a bounded stdlib
first-layer review after native output and before publication. It requires a
matching nominal centred140mm profile, native Skirt first, no startup XY
extrusion/intersection and first-layer deposition within a conservative±69mm
margin. Unsupported/ambiguous/large data fails without an artifact. This is
experimental nominal-path review, **not** a physical or whole-job safety gate.
No generated G-code rewriting, disabled validity checks or printer query. See
PRIMING_REVIEW.md for limits/metadata, exact-tool trials and the native exit0
edge counterexample. Draft03's offline/owned-dummy launcher enables it; normal
02/raw CLI defaults are unchanged. The flag requires slicing, cannot be toggled
by HTTP, and does not approve the changed startup for hardware.

## Offline first

From the repository root, using your own reviewed profile files:

```sh
python3 -m finderlab slice "upload/model.stl" \
  --orca /path/to/orca-slicer \
  --machine local-profiles/finder-machine.json \
  --process local-profiles/finder-process.json \
  --filament local-profiles/pla.json \
  --output upload/model-review.gcode
```

This command **never opens a printer connection**. Without `--output`, G-code is retained as `captures/<run>/sliced.gcode`. Existing outputs are not overwritten. The new output must use `.gcode` or `.g`; no GX container or Finder thumbnail is generated. The output is not rewritten or “repaired” after Orca produces it.

## Slice and upload to the dummy

In terminal 1, start a dummy on a port you control:

```sh
python3 -m finderlab mock --port 9000
```

In terminal 2:

```sh
python3 -m finderlab upload "upload/model.stl" --slice \
  --orca /path/to/orca-slicer \
  --machine local-profiles/finder-machine.json \
  --process local-profiles/finder-process.json \
  --filament local-profiles/pla.json \
  --port 9000 --remote-name "model-review.gcode"
```

Without an override, the remote name is `<original STL stem>.gcode`; the usual bounded ASCII basename policy applies. Use an ASCII override for incompatible model names. A `.gx` override is refused in this combined workflow: renaming plain G-code is not GX conversion. STL without `--slice` remains rejected, and slicing options without `--slice` are rejected instead of silently ignored.

The generated source is retained in the run's capture directory for review/reproduction. A failed upload does not delete it. `--start` is available on the combined command just as on ordinary upload, but is **not a recommendation to print unreviewed slicer output**. It may physically heat/move a target behind a loopback proxy. Non-loopback targets still require `--allow-hardware`; experiment approval and physical supervision are separate requirements. This change is not authorization for an agent hardware trial.

## Invocation and logs

The documented Orca argument contract is:

```text
ORCA --help --datadir DATA
ORCA --slice 0 --arrange 1 --orient 0 --ensure-on-bed
     --load-settings MACHINE.json;PROCESS.json
     --load-filaments FILAMENT.json --datadir DATA --outputdir OUTPUT MODEL.stl
```

Each argument is passed directly without a shell. Model/profile files are bounded snapshots with fixed safe names inside a fresh project-local `.tmp/orca-*` workspace. Help and slicing use an isolated datadir; TMPDIR/TMP/TEMP and XDG config/cache/data paths also point inside the workspace. Semicolon-containing original filenames are safe because they are not used as settings-list elements. Repository paths containing semicolons are unsupported. Exactly **one** nonempty plain `.gcode` output is required; zero/multiple outputs, binary/NUL-containing output, oversized data, failed exit or timeout abort before printer connection.

Manual-mode library/web jobs instead use `--arrange 0` and `placed.stl`, after
the bounded `geometry_transform` helper stage. No other validity check/flag is
disabled; no G-code coordinate rewriting or arbitrary native transforms are used.

Every invocation prints its capture path. `traffic.log` and `events.jsonl` include:

- `slicer_command`: exact argv and stage (`help` or `slice`);
- `slicer_output`: stdout/stderr chunks, readable escaped text and authoritative `data_hex` bytes (not line boundaries); a quota failure truncates further output and aborts the job;
- `slicer_exit`: observed return code on completed commands;
- `slicer_result`: candidate output path, byte length/hash, `toolpaths_validated: false`;
- ordinary `error` events: `preflight`, `slicing`, `connect`, `upload`, or `start_after_upload` as appropriate.

The manifest records input basenames/sizes/SHA-256, executable path, limits and completed stages. Native help output supplies the build/version evidence when the binary prints it; no version is invented. A `slice` recording has no printer sessions. `complete` means the recorder finalized, **not** that slicing/upload/printing succeeded. See [CAPTURES.md](CAPTURES.md). Profiles/model copies in temporary workspaces are removed; logs and the final G-code persist and may contain private model/settings data. Do not commit them.

## Resource limits and trust

Defaults per job:

- model: 64 MiB; each JSON profile: 1 MiB;
- output: 8 MiB (`--max-file-size`);
- help: up to 15 s; slice: 300 s (`--slice-timeout`), with a CPU limit of rounded-up phase seconds + 1;
- child virtual address space: 4096 MiB (`--slice-memory-mib`), not an RSS estimate;
- workspace: 256 MiB (`--slice-work-bytes`) and 4096 entries, monitored every 100 ms; the same byte limit is also a hard **per-file** child limit, not a hard aggregate filesystem quota;
- stdout + stderr: 1 MiB per phase, plus the existing total capture quota;
- one Orca job per repository at a time, enforced by an OS file lock under `.tmp/` (other invocations fail promptly rather than queue indefinitely).

Timeout, cancellation, logging failure and invalid output kill the process group, drain/reap it and clean temporary files. No fixed delay masks a parser error. The workspace monitor can overshoot between samples; use filesystem/container quotas for a hard aggregate disk boundary. The final G-code artifact is separately bounded by `--max-file-size` and is **outside** the recorder's byte counter. Repeated captures/outputs still accumulate; there is no global retention/rotation policy.

This is **not a security sandbox** for an arbitrary executable, native mesh parser, plugin or malicious profile. The trusted executable still has the user's filesystem/network permissions, and can write outside its workspace; only its fixed slicing/help actions are requested. The loopback workbench uses server-owned executables/profiles/targets, a single slot without a queue, bounded storage and no HTTP-supplied native flags/paths. It is restricted to trusted local inputs. A future multi-user/untrusted-mesh service still needs genuine native-code isolation in addition to resource limits; the current wrapper is not that sandbox.

## Evidence and next acceptance step

External interface references, not Finder 2 protocol evidence:

- [Orca CLI actions](https://github.com/OrcaSlicer/OrcaSlicer/wiki/cli_actions): `--slice`, help and default validity checks;
- [Orca CLI misc](https://github.com/OrcaSlicer/OrcaSlicer/wiki/cli_misc): semicolon-separated settings, filament JSON and output/datadir;
- [Orca CLI transforms](https://github.com/OrcaSlicer/OrcaSlicer/wiki/cli_transform): arrange/orient/ensure-on-bed;
- [upstream PrintConfig.cpp](https://github.com/OrcaSlicer/OrcaSlicer/blob/main/src/libslic3r/PrintConfig.cpp): setting names only. Internal enum entries and the accepted flavor list differ; native 2.3.0 rejects Sailfish, and tagged 2.5.0 source excludes it from the accepted list.

These upstream pages/main branch can change. The adapter runtime contains no copied upstream implementation/profile code; private draft profile derivatives retain source/license provenance separately. Downloaded versions and the native help probe are recorded in [ORCA_INSTALL.md](ORCA_INSTALL.md); draft 02 adds native geometry generation, not physical profile validation.

The user explicitly approved the draft 02 offline dialect experiment; native geometry generation now succeeds. Next review its documented G21/M82/M118 and physical homing/clearance blockers, confirm nozzle/material, and retain generated files as review-only until a separately bounded next trial is agreed. Physical start remains a separate approved decision. GX/thumbnail generation and a verified Finder Orca profile remain unimplemented. The standalone page's adapter wiring is now implemented and fake-executable tested; this does not resolve native profile compatibility or validate generated toolpaths.
