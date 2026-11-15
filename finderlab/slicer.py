"""Bounded, shell-free Orca CLI adapter. Does not connect to a printer.

Only trusted local binaries and profiles: resource limits are not a security
sandbox. Toolpath/firmware compatibility remains a separate review task.
"""

import asyncio
from contextlib import contextmanager
from dataclasses import dataclass, replace
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import signal
import stat
import sys
import tempfile

from .slice_settings import normalize_settings, process_overrides
from .model_transform import normalize_transform

ROOT = Path(__file__).resolve().parents[1]
MIB = 1024 * 1024
PROFILE_KEYS = {
    "machine": ("gcode_flavor", "printable_area", "printable_height", "use_relative_e_distances",
                "machine_start_gcode", "machine_end_gcode"),
    "process": ("layer_height", "initial_layer_print_height", "travel_speed", "travel_speed_z"),
    "filament": ("nozzle_temperature", "nozzle_temperature_initial_layer"),
}
REQUIRED_FLAGS = ("--slice", "--load-settings", "--load-filaments", "--outputdir", "--datadir",
                  "--arrange", "--orient", "--ensure-on-bed")


class SliceError(ValueError):
    """No valid output was produced; do not begin printer transfer."""


@dataclass(frozen=True)
class SliceConfig:
    machine: Path
    process: Path
    filament: Path
    orca: str | None = None
    timeout: float = 300.0
    max_model_size: int = 64 * MIB
    max_output_size: int = 8 * MIB
    max_work_bytes: int = 256 * MIB
    max_log_bytes: int = MIB
    memory_mib: int = 4096

    def __post_init__(self):
        if not math.isfinite(self.timeout) or self.timeout <= 0:
            raise SliceError("slice-timeout must be positive and finite")
        for key in ("max_model_size", "max_output_size", "max_work_bytes", "max_log_bytes", "memory_mib"):
            if getattr(self, key) <= 0:
                raise SliceError(f"{key} must be positive")
        if os.name != "posix":
            raise SliceError("The Orca adapter currently requires POSIX process/resource limits (Linux)")
        if any(value is None for value in (self.machine, self.process, self.filament)):
            raise SliceError("Slicing requires --machine, --process and --filament Orca JSON profiles")


@dataclass(frozen=True)
class SliceResult:
    path: Path
    size: int
    sha256: str


def _copy_bounded(source, destination, limit):
    """Snapshot inputs so the invocation/hash refers to exactly the copied bytes."""
    source = Path(source)
    if not source.is_file() or not 0 < source.stat().st_size <= limit:
        raise SliceError(f"Expected a regular file containing 1–{limit} bytes: {source}")
    size = 0
    digest = hashlib.sha256()
    with source.open("rb") as reader, destination.open("xb") as writer:
        while data := reader.read(65536):
            size += len(data)
            if size > limit:
                raise SliceError(f"Input exceeds {limit} bytes: {source}")
            digest.update(data)
            writer.write(data)
    if size == 0:
        raise SliceError(f"Empty input: {source}")
    return {"name": source.name, "size": size, "sha256": digest.hexdigest()}


def _check_profile(path, kind):
    try:
        config = json.loads(path.read_bytes())
    except (ValueError, RecursionError) as exc:
        raise SliceError(f"Invalid Orca {kind} JSON profile") from exc
    if not isinstance(config, dict) or config.get("type") != kind:
        raise SliceError(f"Expected Orca JSON profile with type={kind!r}")
    # Do not let profile-defined host post-processing become an implicit shell.
    # Inheritance is deliberately not resolved from the user's global datadir.
    if config.get("inherits"):
        raise SliceError(f"{kind} profile must be flattened/self-contained (inherits must be empty)")
    missing = [key for key in PROFILE_KEYS[kind]
               if key not in config or config[key] is None or config[key] == "" or config[key] == []]
    if missing:
        raise SliceError(f"{kind} profile lacks explicit settings: {', '.join(missing)}; do not fall back to generic defaults")
    def inspect(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if key == "post_process" and item and item != [""]:
                    raise SliceError("Host post_process scripts are not permitted in slicing profiles")
                inspect(item)
        elif isinstance(value, list):
            for item in value:
                inspect(item)
    try:
        inspect(config)
    except RecursionError as exc:
        raise SliceError("Profile nesting is too deep") from exc


def _work_size(work, limit):
    count = total = 0
    for directory, dirs, files in os.walk(work, followlinks=False):
        for name in dirs + files:
            path = Path(directory) / name
            try:
                info = path.lstat()
            except FileNotFoundError:
                continue  # Native temporary files may disappear during the scan.
            count += 1
            if stat.S_ISLNK(info.st_mode) or not (stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode)):
                raise SliceError("Slicer created a symlink or special file")
            if stat.S_ISREG(info.st_mode):
                total += info.st_size
            if count > 4096 or total > limit:
                raise SliceError("Slicer workspace byte/file limit exceeded")


async def _run(executable, arguments, work, config, capture, *, stage, timeout):
    label = "Geometry transform" if stage == "geometry_transform" else f"Orca {stage}"
    command = [executable, *map(str, arguments)]
    capture.event("slicer_command", stage=stage, argv=command)
    wrapper = Path(__file__).with_name("_slicer_worker.py")
    spawn = asyncio.create_task(asyncio.create_subprocess_exec(
        sys.executable, str(wrapper), str(config.memory_mib * MIB), str(config.max_work_bytes),
        str(max(1, math.ceil(timeout) + 1)), *command,
        cwd=work, env={**os.environ, "TMPDIR": str(work / "tmp"), "TMP": str(work / "tmp"),
                       "TEMP": str(work / "tmp"), "XDG_CACHE_HOME": str(work / "cache"),
                       "XDG_CONFIG_HOME": str(work / "config"), "XDG_DATA_HOME": str(work / "data")},
        stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE, start_new_session=True,
    ))
    try:
        process = await asyncio.shield(spawn)
    except asyncio.CancelledError:
        # Do not lose the process handle if cancellation races process creation.
        process = await spawn
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        await process.communicate()
        raise
    total = 0
    help_bytes = {"stdout": bytearray(), "stderr": bytearray()}
    async def drain(reader, stream):
        nonlocal total
        while chunk := await reader.read(4096):
            total += len(chunk)
            if total > config.max_log_bytes:
                raise SliceError("Slicer output log limit exceeded")
            capture.event("slicer_output", stage=stage, stream=stream, data_hex=chunk.hex(),
                          text=chunk.decode("utf-8", "backslashreplace"))
            if stage == "help":
                help_bytes[stream].extend(chunk)
    async def watch():
        while True:
            _work_size(work, config.max_work_bytes)
            await asyncio.sleep(0.1)  # Resource monitor, not a protocol/parser delay.
    tasks = [asyncio.create_task(drain(process.stdout, "stdout")),
             asyncio.create_task(drain(process.stderr, "stderr")),
             asyncio.create_task(process.wait()), asyncio.create_task(watch())]
    try:
        async with asyncio.timeout(timeout):
            pending = set(tasks[:3])
            while pending:
                done, _ = await asyncio.wait(pending | {tasks[3]}, return_when=asyncio.FIRST_COMPLETED)
                for task in done:
                    task.result()
                pending -= done
        capture.event("slicer_exit", stage=stage, returncode=process.returncode)
        if process.returncode:
            raise SliceError(f"{label} exited with code {process.returncode}; see traffic.log")
        _work_size(work, config.max_work_bytes)
        return bytes(help_bytes["stdout"]) + b"\n" + bytes(help_bytes["stderr"])
    except TimeoutError as exc:
        raise SliceError(f"{label} timed out after {timeout:g}s") from exc
    finally:
        # Kill the entire job group even when the launcher exits before children.
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        # Drain unread pipe buffers after killing, without logging more bytes.
        # wait() alone can deadlock when a quota failure paused a full pipe.
        await process.communicate()


@contextmanager
def _slice_slot(scratch):
    import fcntl  # POSIX only; do not affect non-slicing commands on other OSes.
    with (scratch / "orca.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise SliceError("Another Orca job is running in this workspace; try again after it finishes") from exc
        yield


async def slice_model(source, output, config: SliceConfig, *, capture, settings=None, transform=None) -> SliceResult:
    """STL -> exactly one plain G-code file. Never overwrite an existing output.

    The caller owns the output/capture lifetime. Temporary inputs and tool data
    are removed even on failure/cancellation; failed output is never published.
    """
    chosen_transform = normalize_transform(transform)
    chosen_settings = normalize_settings(settings)
    overrides = process_overrides(chosen_settings)
    source, output = Path(source), Path(output)
    if source.suffix.lower() not in (".stl", ".3mf"):
        raise SliceError("Slicing accepts STL or geometry-only core mesh 3MF")
    if output.suffix.lower() not in (".gcode", ".g"):
        raise SliceError("Slicing output must be .gcode or .g, not GX (no container conversion)")
    if output.exists() or output.is_symlink():
        raise SliceError(f"Refusing to overwrite slicing output: {output}")
    executable = config.orca or shutil.which("orca-slicer") or shutil.which("OrcaSlicer")
    executable = shutil.which(str(executable)) if executable else None
    if not executable:
        raise SliceError("OrcaSlicer not found; install it separately and specify --orca /path/to/executable")
    executable = str(Path(executable).resolve())
    scratch = ROOT / ".tmp"
    scratch.mkdir(mode=0o700, exist_ok=True)
    with _slice_slot(scratch), tempfile.TemporaryDirectory(prefix="orca-", dir=scratch) as directory:
        work = Path(directory)
        if ";" in str(work):
            raise SliceError("Orca settings paths cannot contain semicolons")
        for name in ("tmp", "data", "output", "cache", "config"):
            (work / name).mkdir()
        model_snapshot = work / ("source.3mf" if source.suffix.lower() == ".3mf" else "model.stl")
        inputs = {"model": _copy_bounded(source, model_snapshot, config.max_model_size)}
        capture.manifest["metadata"]["slicing_inputs"] = inputs
        capture.manifest["metadata"]["model_transform"] = chosen_transform
        if source.suffix.lower() == ".3mf":
            from .model_3mf import geometry_to_stl
            try:
                geometry = geometry_to_stl(model_snapshot, work / "model.stl", max_output=config.max_model_size)
            except ValueError as exc:
                raise SliceError(str(exc)) from exc
            capture.manifest["metadata"]["geometry_import"] = geometry
            capture.event("geometry_import", **geometry)
        for kind in ("machine", "process", "filament"):
            path = work / (kind + ".json")
            inputs[kind] = _copy_bounded(getattr(config, kind), path, MIB)
            _check_profile(path, kind)
        model_path = work / "model.stl"
        if chosen_transform is not None:
            capture.manifest["metadata"]["geometry_transform_limits"] = {
                "memory_mib": min(512, config.memory_mib), "timeout": min(30, config.timeout),
                "max_source_bytes": 32 * MIB, "max_triangles": 200000}
            (work / "transform.json").write_text(json.dumps(chosen_transform))
            await _run(sys.executable, [Path(__file__).with_name("model_transform.py"), model_path,
                       work / "placed.stl", work / "transform.json", work / "machine.json", work / "transform-result.json"],
                       work, replace(config, memory_mib=min(512, config.memory_mib)), capture,
                       stage="geometry_transform", timeout=min(30, config.timeout))
            report_path = work / "transform-result.json"
            if not report_path.is_file() or report_path.stat().st_size > 4096:
                raise SliceError("Missing/oversized geometry transform report")
            report = json.loads(report_path.read_bytes())
            capture.manifest["metadata"]["geometry_transform"] = report
            capture.event("geometry_transform", **report)
            model_path = work / "placed.stl"
        # Apply only the typed quality allowlist to a private profile snapshot.
        # Never edit the server-owned originals, templates, machine or filament.
        process_path = work / "process.json"
        if overrides:
            effective = json.loads(process_path.read_bytes())
            effective.update(overrides)
            encoded = (json.dumps(effective, indent=2) + "\n").encode()
            if len(encoded) > MIB:
                raise SliceError("Effective process profile exceeds 1 MiB")
            process_path.write_bytes(encoded)
            _check_profile(process_path, "process")
        effective_hash = hashlib.sha256(process_path.read_bytes()).hexdigest()
        effective_process = json.loads(process_path.read_bytes())
        quality = {key: effective_process.get(key) for key in
                   ("layer_height", "initial_layer_print_height", "brim_type", "brim_width", "brim_object_gap",
                    "xy_hole_compensation", "xy_contour_compensation")}
        capture.manifest["metadata"].update(slice_settings=chosen_settings, process_overrides=overrides,
                                              effective_process_sha256=effective_hash, effective_quality=quality)
        capture.event("slicer_settings", settings=chosen_settings, process_overrides=overrides,
                      source_process_sha256=inputs["process"]["sha256"], effective_process_sha256=effective_hash,
                      effective_quality=quality)
        capture.manifest["metadata"]["orca_executable"] = executable
        capture.manifest["metadata"]["slicing_limits"] = {
            key: getattr(config, key) for key in ("timeout", "max_model_size", "max_output_size",
                                                 "max_work_bytes", "max_log_bytes", "memory_mib")
        }
        _work_size(work, config.max_work_bytes)
        help_data = await _run(executable, ["--help", "--datadir", work / "data"], work, config, capture,
                               stage="help", timeout=min(15, config.timeout))
        for flag in REQUIRED_FLAGS:
            if flag.encode() not in help_data:
                raise SliceError(f"Installed Orca CLI does not advertise required flag {flag}; check version/build")
        await _run(executable, ["--slice", "0", "--arrange", "0" if chosen_transform is not None else "1", "--orient", "0", "--ensure-on-bed",
                               "--load-settings", str(work / "machine.json") + ";" + str(work / "process.json"),
                               "--load-filaments", work / "filament.json", "--datadir", work / "data",
                               "--outputdir", work / "output", model_path],
                   work, config, capture, stage="slice", timeout=config.timeout)
        _work_size(work, config.max_work_bytes)  # Recheck after the entire process group is stopped.
        candidates = list((work / "output").rglob("*"))
        candidates = [p for p in candidates if p.is_file() and p.suffix.lower() == ".gcode"]
        if len(candidates) != 1:
            raise SliceError(f"Expected exactly one generated .gcode file, got {len(candidates)}")
        staged = candidates[0]
        if not 0 < staged.stat().st_size <= config.max_output_size:
            raise SliceError("Generated G-code is empty or exceeds the output byte limit")
        with staged.open("rb") as reader:
            data = reader.read(config.max_output_size + 1)
        if not data or len(data) > config.max_output_size or b"\x00" in data or data.startswith(b"GCDE"):
            raise SliceError("Expected bounded plain G-code, not binary data")
        result = SliceResult(output, len(data), hashlib.sha256(data).hexdigest())
        capture.event("slicer_result", output=str(output), size=result.size, sha256=result.sha256,
                      toolpaths_validated=False)
        output.parent.mkdir(parents=True, exist_ok=True)
        writer = output.open("xb")  # Fail without touching someone else's existing file.
        try:
            with writer:
                writer.write(data)
        except BaseException:
            output.unlink(missing_ok=True)
            raise
        return result
