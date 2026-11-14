"""Orca adapter/CLI control tests with an independent fake executable, not slicing evidence."""

import asyncio
from contextlib import redirect_stdout
from dataclasses import replace
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import AsyncMock, patch

from finderlab.__main__ import parser
from finderlab.capture import Capture
from finderlab.cli_client import PreflightError, run_client
from finderlab.client import ClientConfig
from finderlab.slicer import SliceConfig, SliceError, slice_model
from finderlab.simulator import MockConfig, MockPrinter
from helpers import events, workspace_tempdir

PAYLOAD = b"; synthetic adapter-test output only\r\nG90\nG92 E0\n; ~M29 ok\n"
# Deliberately independent from the adapter's REQUIRED_FLAGS/argument builder.
FAKE = '''import json, os, pathlib, resource, sys, time
assert 0 < resource.getrlimit(resource.RLIMIT_AS)[0] <= 4*1024**3
assert resource.getrlimit(resource.RLIMIT_FSIZE)[0] <= 256*1024**2
assert 0 < resource.getrlimit(resource.RLIMIT_CPU)[0] <= 301
assert resource.getrlimit(resource.RLIMIT_CORE) == (0, 0)
assert os.getpgrp() == os.getpid()
args = sys.argv[1:]
if "--help" in args:
    if BEHAVIOR == "slow_help": time.sleep(30)
    print("OrcaSlicer FAKE - control tests only")
    if BEHAVIOR != "old":
        print("--slice --load-settings --load-filaments --outputdir --datadir --arrange --orient --ensure-on-bed")
    sys.exit(0)
def value(flag):
    return args[args.index(flag)+1]
assert value("--slice") == "0"
assert value("--arrange") == "1" and value("--orient") == "0"
assert "--ensure-on-bed" in args
settings = value("--load-settings").split(";")
assert [json.loads(pathlib.Path(p).read_text())["type"] for p in settings] == ["machine", "process"]
assert json.loads(pathlib.Path(value("--load-filaments")).read_text())["type"] == "filament"
assert pathlib.Path(value("--datadir")).is_dir()
assert pathlib.Path(args[-1]).name == "model.stl"
assert os.environ["TMPDIR"] == str(pathlib.Path.cwd()/"tmp")
assert not any(flag in args for flag in ("--upload", "--print", "--no-check"))
print("READY " + str(os.getpid()), flush=True)
if BEHAVIOR == "slow": time.sleep(30)
if BEHAVIOR == "fail":
    sys.stderr.buffer.write(b"synthetic Orca error\\xff\\n")
    sys.exit(7)
if BEHAVIOR == "flood":
    sys.stderr.buffer.write(b"x" * (2*1024*1024))
    sys.exit(0)
output = pathlib.Path(value("--outputdir"))
if BEHAVIOR == "disk": (output/"too-large.bin").write_bytes(b"x"*65536)
if BEHAVIOR == "missing": sys.exit(0)
if BEHAVIOR == "symlink":
    (output/"plate_1.gcode").symlink_to(pathlib.Path(args[-1]))
    sys.exit(0)
data = PAYLOAD
if BEHAVIOR == "empty": data = b""
if BEHAVIOR == "large": data = b"x" * 4096
if BEHAVIOR == "binary": data = b"GCDE\\0binary"
(output/"plate_1.gcode").write_bytes(data)
if BEHAVIOR == "multiple": (output/"plate_2.gcode").write_bytes(data)
'''


@unittest.skipUnless(os.name == "posix", "POSIX resource-limited slicing adapter")
class SlicerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = workspace_tempdir()
        self.root = Path(self.temp.name)
        self.source = self.root / "model ; with spaces.STL"
        self.source.write_text("solid synthetic\nendsolid synthetic\n")
        self.output = self.root / "result.gcode"
        self.fake = self.root / "fake orca"
        self.set_behavior("ok")
        profiles = {}
        for kind in ("machine", "process", "filament"):
            path = self.root / (kind + ".json")
            values = {
                "machine": {"gcode_flavor": "sailfish", "printable_area": ["-70x-70", "70x-70", "70x70", "-70x70"],
                            "printable_height": "140", "use_relative_e_distances": "0",
                            "machine_start_gcode": "; synthetic test", "machine_end_gcode": "; synthetic test"},
                "process": {"layer_height": "0.18", "initial_layer_print_height": "0.27",
                            "travel_speed": "80", "travel_speed_z": "7"},
                "filament": {"nozzle_temperature": ["220"], "nozzle_temperature_initial_layer": ["220"]},
            }[kind]
            path.write_text(json.dumps({"type": kind, "name": "Synthetic test only", "inherits": "", **values}))
            profiles[kind] = path
        self.config = SliceConfig(**profiles, orca=str(self.fake), timeout=3)
        self.capture = Capture(self.root / "captures", "slice")

    async def asyncTearDown(self):
        self.capture.close()
        self.temp.cleanup()

    def set_behavior(self, behavior):
        self.fake.write_text(f"#!{sys.executable}\nBEHAVIOR = {behavior!r}\nPAYLOAD = {PAYLOAD!r}\n" + FAKE)
        self.fake.chmod(0o700)

    async def slice(self, config=None):
        return await slice_model(self.source, self.output, config or self.config, capture=self.capture)

    async def invoke(self, *args):
        with redirect_stdout(io.StringIO()):
            return await run_client(*args)

    def options(self, mode="upload", *extra):
        args = [mode, str(self.source), "--orca", str(self.fake)]
        if mode == "upload":
            args.append("--slice")
        for kind in ("machine", "process", "filament"):
            args += ["--" + kind, str(getattr(self.config, kind))]
        args += ["--capture-dir", str(self.root / "cli-captures"), *extra]
        return vars(parser().parse_args(args))

    async def test_slice_snapshots_inputs_and_publishes_exact_single_output(self):
        result = await self.slice()
        self.assertEqual(self.output.read_bytes(), PAYLOAD)
        self.assertEqual(result.size, len(PAYLOAD))
        self.assertEqual(result.sha256, hashlib.sha256(PAYLOAD).hexdigest())
        self.assertEqual(self.capture.manifest["metadata"]["slicing_inputs"]["model"]["sha256"],
                         hashlib.sha256(self.source.read_bytes()).hexdigest())
        command = [e for e in events(self.capture) if e["type"] == "slicer_command" and e["stage"] == "slice"][0]
        self.assertFalse(Path(command["argv"][-1]).parent.exists(), "Scratch data not cleaned")
        self.assertEqual([e["returncode"] for e in events(self.capture) if e["type"] == "slicer_exit"], [0, 0])
        with self.assertRaisesRegex(SliceError, "overwrite"):
            await self.slice()
        self.assertEqual(self.output.read_bytes(), PAYLOAD)

    async def test_quality_options_only_change_private_process_snapshot(self):
        originals = {kind: getattr(self.config, kind).read_bytes() for kind in ("machine", "process", "filament")}
        check = '''
effective = json.loads(pathlib.Path(settings[1]).read_text())
assert effective["layer_height"] == "0.12"
assert effective["initial_layer_print_height"] == "0.27"
assert effective["brim_type"] == "outer_only"
assert effective["brim_width"] == "5"
assert "machine_start_gcode" not in effective and "retraction_length" not in effective
'''
        self.fake.write_text(self.fake.read_text().replace('print("READY "', check + '\nprint("READY "'))
        settings = {"layer_height": 0.12, "brim": "outer", "brim_width": 5}
        result = await slice_model(self.source, self.output, self.config, capture=self.capture, settings=settings)
        self.assertEqual(result.path.read_bytes(), PAYLOAD)
        for kind, raw in originals.items():
            self.assertEqual(getattr(self.config, kind).read_bytes(), raw)
        metadata = self.capture.manifest["metadata"]
        self.assertEqual(metadata["slice_settings"], settings)
        self.assertEqual(metadata["process_overrides"], {"layer_height": "0.12", "brim_type": "outer_only", "brim_width": "5"})
        self.assertEqual(metadata["effective_quality"]["initial_layer_print_height"], "0.27")
        self.assertEqual(metadata["slicing_inputs"]["process"]["sha256"], hashlib.sha256(originals["process"]).hexdigest())
        self.assertNotEqual(metadata["effective_process_sha256"], metadata["slicing_inputs"]["process"]["sha256"])
        self.assertEqual(metadata["slicing_inputs"]["machine"]["sha256"], hashlib.sha256(originals["machine"]).hexdigest())
        self.assertEqual(metadata["slicing_inputs"]["filament"]["sha256"], hashlib.sha256(originals["filament"]).hexdigest())

    async def test_default_quality_options_preserve_profile_bytes(self):
        await self.slice()
        metadata = self.capture.manifest["metadata"]
        self.assertEqual(metadata["process_overrides"], {})
        self.assertEqual(metadata["effective_process_sha256"], metadata["slicing_inputs"]["process"]["sha256"])

    async def test_bad_outputs_and_failed_exit_never_publish(self):
        for behavior in ("missing", "multiple", "empty", "binary", "symlink", "fail", "old", "large", "flood"):
            with self.subTest(behavior=behavior):
                self.set_behavior(behavior)
                with self.assertRaises(SliceError):
                    await self.slice(replace(self.config, max_output_size=1024, max_log_bytes=65536))
                self.assertFalse(self.output.exists())
        failures = [e for e in events(self.capture) if e["type"] == "slicer_output" and "synthetic Orca error" in e["text"]]
        self.assertEqual(bytes.fromhex(failures[0]["data_hex"]), b"synthetic Orca error\xff\n")

    async def test_timeout_and_cancellation_kill_and_reap_process(self):
        self.set_behavior("slow")
        with self.assertRaisesRegex(SliceError, "timed out"):
            await self.slice(replace(self.config, timeout=1))
        ready = asyncio.Event()
        pid = None
        original = self.capture.event
        def observe(kind, **fields):
            nonlocal pid
            result = original(kind, **fields)
            if kind == "slicer_output" and "READY " in fields["text"]:
                pid = int(fields["text"].split("READY ")[1].strip())
                ready.set()
            return result
        self.capture.event = observe
        task = asyncio.create_task(self.slice())
        try:
            await asyncio.wait_for(ready.wait(), 3)
            with self.assertRaisesRegex(SliceError, "Another Orca job"):
                await self.slice()
        finally:
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
        with self.assertRaises(ProcessLookupError):
            os.kill(pid, 0)
        self.assertFalse(self.output.exists())
        command = [e for e in events(self.capture) if e["type"] == "slicer_command"][-1]
        self.assertFalse(Path(command["argv"][-1]).parent.exists())

    async def test_cancellation_during_process_creation_retains_cleanup_handle(self):
        self.set_behavior("slow_help")
        spawned, release = asyncio.Event(), asyncio.Event()
        original = asyncio.create_subprocess_exec
        processes, workspaces = [], []
        async def delayed(*args, **kwargs):
            process = await original(*args, **kwargs)
            processes.append(process)
            workspaces.append(Path(kwargs["cwd"]))
            spawned.set()
            await release.wait()
            return process
        with patch("finderlab.slicer.asyncio.create_subprocess_exec", delayed):
            task = asyncio.create_task(self.slice())
            try:
                await asyncio.wait_for(spawned.wait(), 3)
            finally:
                task.cancel()
                release.set()
                with self.assertRaises(asyncio.CancelledError):
                    await task
        self.assertIsNotNone(processes[0].returncode)
        self.assertFalse(self.output.exists())
        self.assertFalse(workspaces[0].exists())

    async def test_profiles_and_source_validation_precede_process(self):
        self.config.machine.write_text('{"type":"machine", "inherits":"unreviewed parent"}')
        with self.assertRaisesRegex(SliceError, "self-contained"):
            await self.slice()
        for data in ('{"type":"machine","post_process":["touch /not-allowed"]}', '[]', '{bad'):
            self.config.machine.write_text(data)
            with self.assertRaises(SliceError):
                await self.slice()
        self.assertFalse(any(e["type"] == "slicer_command" for e in events(self.capture)))
        with self.assertRaisesRegex(SliceError, "output"):
            await slice_model(self.source, self.root / "fake.gx", self.config, capture=self.capture)
        with self.assertRaises(SliceError):
            await self.slice(replace(self.config, max_model_size=1))
        with self.assertRaisesRegex(SliceError, "not found"):
            await self.slice(replace(self.config, orca=str(self.root / "absent")))

    async def test_resource_and_capture_limits_prevent_output(self):
        with self.assertRaisesRegex(SliceError, "workspace"):
            await self.slice(replace(self.config, max_work_bytes=1))
        self.set_behavior("disk")
        with self.assertRaises(SliceError):
            await self.slice(replace(self.config, max_work_bytes=32768))
        self.assertFalse(self.output.exists())
        self.capture.max_bytes = 64
        with self.assertRaises(OSError):
            await self.slice()
        self.assertFalse(self.output.exists())

    async def test_recording_failure_during_child_output_aborts_and_cleans(self):
        self.set_behavior("flood")
        original = self.capture.event
        def limit_after_spawn(kind, **fields):
            result = original(kind, **fields)
            if kind == "slicer_command" and fields["stage"] == "slice":
                self.capture.max_bytes = self.capture.written + 1
            return result
        self.capture.event = limit_after_spawn
        with self.assertRaises(OSError):
            await asyncio.wait_for(self.slice(), 5)
        self.assertTrue(self.capture.failed)
        self.assertFalse(self.output.exists())

    async def test_cli_offline_slice_never_opens_connection(self):
        with patch("finderlab.client.asyncio.open_connection", new_callable=AsyncMock) as connect:
            result = await self.invoke(ClientConfig(), "slice", self.options("slice", "--output", str(self.output)))
            connect.assert_not_awaited()
        self.assertEqual(result.path.read_bytes(), PAYLOAD)
        manifest = json.loads(next((self.root / "cli-captures").glob("*/manifest.json")).read_text())
        self.assertEqual(manifest["mode"], "slice")
        self.assertEqual(manifest["sessions"], [])
        self.assertTrue(manifest["metadata"]["slicing_confirmed"])

    async def test_upload_slices_before_connect_and_does_not_start(self):
        async with MockPrinter(MockConfig(port=0)) as mock:
            await self.invoke(ClientConfig(port=mock.address[1]), "upload",
                              self.options("upload", "--remote-name", "chosen.gcode"))
            self.assertEqual(mock.files["chosen.gcode"], PAYLOAD)
            self.assertIsNone(mock.active_file)
        manifest_path = next((self.root / "cli-captures").glob("*/manifest.json"))
        manifest = json.loads(manifest_path.read_text())
        self.assertTrue(manifest["metadata"]["slicing_confirmed"])
        self.assertTrue(manifest["metadata"]["upload_confirmed"])
        records = [json.loads(line) for line in (manifest_path.parent / "events.jsonl").read_text().splitlines()]
        types = [e["type"] for e in records]
        self.assertLess(types.index("slicer_result"), types.index("connection_open"))

    async def test_slice_upload_can_explicitly_start_exact_default_destination(self):
        self.source = self.source.rename(self.root / "box.STL")
        async with MockPrinter(MockConfig(port=0)) as mock:
            await self.invoke(ClientConfig(port=mock.address[1]), "upload", self.options("upload", "--start"))
            self.assertEqual(mock.files["box.gcode"], PAYLOAD)
            self.assertEqual(mock.active_file, "box.gcode")

    async def test_failed_slicing_and_gx_override_never_connect_or_start(self):
        for behavior in ("fail", "missing", "old"):
            self.set_behavior(behavior)
            with patch("finderlab.client.asyncio.open_connection", new_callable=AsyncMock) as connect:
                with self.assertRaises(SliceError):
                    await self.invoke(ClientConfig(), "upload", self.options("upload", "--start", "--remote-name", "model.gcode"))
                connect.assert_not_awaited()
        with patch("finderlab.client.asyncio.open_connection", new_callable=AsyncMock) as connect:
            with self.assertRaises(PreflightError):
                await self.invoke(ClientConfig(), "upload", self.options("upload", "--remote-name", "not-a-container.gx"))
            connect.assert_not_awaited()
        phases = []
        for manifest_path in (self.root / "cli-captures").glob("*/manifest.json"):
            manifest = json.loads(manifest_path.read_text())
            self.assertEqual(manifest["sessions"], [])
            self.assertNotIn("upload_confirmed", manifest["metadata"])
            records = [json.loads(line) for line in (manifest_path.parent / "events.jsonl").read_text().splitlines()]
            phases.extend(e["phase"] for e in records if e["type"] == "error")
        self.assertCountEqual(phases, ["slicing", "slicing", "slicing", "preflight"])

    async def test_explicit_slicing_and_limits_are_required(self):
        for kwargs in ({"timeout": 0}, {"timeout": float("nan")}, {"memory_mib": 0}, {"machine": None}):
            with self.assertRaises(SliceError):
                replace(self.config, **kwargs)
        with self.assertRaisesRegex(SliceError, "STL"):
            await slice_model(self.root / "model.3mf", self.output, self.config, capture=self.capture)
        for with_profiles in (False, True):
            options = self.options("upload")
            options["slice"] = False
            if not with_profiles:
                for key in ("machine", "process", "filament", "orca"):
                    options[key] = None
            with patch("finderlab.client.asyncio.open_connection", new_callable=AsyncMock) as connect:
                with self.assertRaises(PreflightError):
                    await self.invoke(ClientConfig(), "upload", options)
                connect.assert_not_awaited()

    async def test_slice_limit_flag_without_opt_in_is_not_silently_ignored(self):
        gcode = self.root / "existing.gcode"
        gcode.write_bytes(PAYLOAD)
        options = vars(parser().parse_args(["upload", str(gcode), "--slice-timeout", "1",
                                           "--capture-dir", str(self.root / "cli-captures")]))
        with patch("finderlab.client.asyncio.open_connection", new_callable=AsyncMock) as connect:
            with self.assertRaisesRegex(PreflightError, "require --slice"):
                await self.invoke(ClientConfig(), "upload", options)
            connect.assert_not_awaited()

    async def test_publish_flush_error_removes_output(self):
        original = Path.open
        class FlushError:
            def __init__(self, writer): self.writer = writer
            def __enter__(self): return self.writer
            def __exit__(self, *args):
                self.writer.close()
                raise OSError("synthetic flush error")
        def failing(path, *args, **kwargs):
            file = original(path, *args, **kwargs)
            return FlushError(file) if path == self.output and args == ("xb",) else file
        with patch.object(Path, "open", failing):
            with self.assertRaisesRegex(OSError, "flush error"):
                await self.slice()
        self.assertFalse(self.output.exists())

    async def test_real_cli_subprocess_slice_command(self):
        root = Path(__file__).resolve().parents[1]
        options = []
        for kind in ("machine", "process", "filament"):
            options.extend(["--" + kind, str(getattr(self.config, kind))])
        process = await asyncio.create_subprocess_exec(
            sys.executable, "-m", "finderlab", "slice", str(self.source), "--orca", str(self.fake),
            *options, "--output", str(self.output), "--capture-dir", str(self.root / "cli-captures"),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            cwd=root, env={**os.environ, "TMPDIR": str(root / ".tmp")},
        )
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), 8)
            self.assertEqual(process.returncode, 0, stderr.decode())
            self.assertIn(b"Slicing complete:", stdout)
            self.assertNotIn(b"Target:", stdout)
            self.assertEqual(self.output.read_bytes(), PAYLOAD)
        finally:
            if process.returncode is None:
                process.kill()
                await process.communicate()
