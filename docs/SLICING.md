# OrcaSlicer CLI integration

## Status and boundaries

Implemented: `slice MODEL.stl` for offline export, and `upload MODEL.stl --slice` for sequential STL → Orca → plain G-code → the existing uploader. The async adapter is `finderlab/slicer.py::slice_model`; it does not import or invoke the printer client. The combined CLI does not open a printer connection until slicing has succeeded. Upload-only remains the default; the existing explicit `--start` still means save confirmation → READY check → start. There is no automatic stop or retry.

**Not verified here:** actual Orca slicing, an Orca Finder 2 profile, physical plain-G-code support, or safe generated toolpaths. Official 2.3.0/2.5.0 AppImages are now downloaded/extracted locally, but native execution is blocked by runtime dependencies (and the newer build's glibc requirement). See [ORCA_INSTALL.md](ORCA_INSTALL.md) for exact paths, provenance, host instructions and pending approval. Automated tests use an independent fake executable plus fresh ephemeral dummy printers; they test orchestration/limits, not geometry or Orca compatibility. No native slicing or physical printer trial was performed; subsequent native help attempts failed in the runtime/loader before CLI validation.

This is a CLI/library foundation for a future local web API, **not an implemented HTTP endpoint**. The user request's “sdl” is interpreted as **STL**. 3MF/OBJ/SDL inputs are not accepted in this first adapter. STL coordinates are interpreted as millimetres: no automatic unit conversion, scaling, repair or auto-orientation. Orca is asked to arrange the object and ensure it is on the bed, using the supplied machine profile.

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

This is **not a security sandbox** for an arbitrary executable, native mesh parser, plugin or malicious profile. The trusted executable still has the user's filesystem/network permissions, and can write outside its workspace; only its fixed slicing/help actions are requested. A future web API must use server-owned executables/profiles/targets, isolate native slicing of untrusted meshes, enforce a bounded queue and total storage, and must not accept arbitrary CLI flags or paths from HTTP clients.

## Evidence and next acceptance step

External interface references, not Finder 2 protocol evidence:

- [Orca CLI actions](https://github.com/OrcaSlicer/OrcaSlicer/wiki/cli_actions): `--slice`, help and default validity checks;
- [Orca CLI misc](https://github.com/OrcaSlicer/OrcaSlicer/wiki/cli_misc): semicolon-separated settings, filament JSON and output/datadir;
- [Orca CLI transforms](https://github.com/OrcaSlicer/OrcaSlicer/wiki/cli_transform): arrange/orient/ensure-on-bed;
- [upstream PrintConfig.cpp](https://github.com/OrcaSlicer/OrcaSlicer/blob/main/src/libslic3r/PrintConfig.cpp): reported setting names and Sailfish enum availability, not proof that a particular packaged version or profile works here.

These upstream pages/main branch can change. No upstream implementation/profile code was copied. Downloaded versions are now recorded in [ORCA_INSTALL.md](ORCA_INSTALL.md); successful native CLI/build validation is still pending.

Next: provide the host Orca executable/version and exported machine/process/filament profiles (including any inherited parents), resolve/review them, run **offline slicing only**, inspect output plus logs, then transfer to a fresh dummy. Physical start remains a separate approved decision. GX/thumbnail generation, a verified Finder Orca profile and the web API remain unimplemented.
