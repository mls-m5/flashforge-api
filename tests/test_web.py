"""Standalone HTTP/UI contracts; ephemeral loopback only, fake Orca, no hardware."""

import asyncio
from dataclasses import replace
import hashlib
import json
import os
import signal
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

from finderlab.client import ClientConfig, FinderClient
from finderlab.simulator import MockConfig, MockPrinter
from finderlab.slicer import SliceConfig
from finderlab.web import MODEL_LIMIT, PRINT_LIMIT, WebCapture, WebConfig, WebServer, Workbench, serve_workbench, suggested_name
from helpers import workspace_tempdir
from test_slicer import FAKE, PAYLOAD


@unittest.skipUnless(os.name == "posix", "Web workspace locking currently requires POSIX")
class WebTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = workspace_tempdir(); self.root = Path(self.temp.name)
        self.mock = await MockPrinter(MockConfig(port=0)).__aenter__()
        self.config = WebConfig(port=0, data_dir=self.root / "web-data", enable_upload=True,
                                client=ClientConfig(port=self.mock.address[1]))
        self.server = await WebServer(self.config).__aenter__()

    async def asyncTearDown(self):
        await self.server.__aexit__(None, None, None)
        await self.mock.__aexit__(None, None, None)
        self.temp.cleanup()

    async def request(self, method, path, body=b"", headers=None, *, early_eof=False):
        base = {"Host": self.server.authority, "Content-Length": str(len(body))}
        if method == "POST":
            base.update({"Content-Type": "application/json", "Origin": "http://" + self.server.authority,
                         "X-Finder-Token": self.server.token})
        base.update(headers or {})
        raw = (f"{method} {path} HTTP/1.1\r\n" + "".join(f"{k}: {v}\r\n" for k, v in base.items()) + "\r\n").encode()
        reader, writer = await asyncio.open_connection(*self.server.address)
        try:
            # Split header CRLF without timing sleeps.
            writer.write(raw[:-1]); await writer.drain()
            writer.write(raw[-1:] + body); await writer.drain()
            if early_eof: writer.write_eof()
            response = await asyncio.wait_for(reader.read(), 4)
        finally:
            writer.close(); await writer.wait_closed()
        head, content = response.split(b"\r\n\r\n", 1)
        status = int(head.split(b" ")[1])
        return status, content

    async def post(self, path, data):
        return await self.request("POST", path, json.dumps(data).encode())

    async def file(self, name, data=b"; synthetic\x00ok\r\n~M29" * 500):
        return await self.request("POST", "/api/file?name=" + name, data,
                                  {"Content-Type": "application/octet-stream"})

    async def finish(self):
        await asyncio.wait_for(asyncio.shield(self.server.work.task), 5)
        return self.server.work.state

    async def test_cli_dummy_rejects_external_endpoint_options(self):
        process = await asyncio.create_subprocess_exec(
            sys.executable, "-m", "finderlab", "web", "--dummy", "--target-port", "9000",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        _, error = await asyncio.wait_for(process.communicate(), 5)
        self.assertEqual(process.returncode, 2)
        self.assertIn(b"owns its endpoint", error)

    async def test_cli_starts_disabled_and_shuts_down_cleanly(self):
        for signum in (signal.SIGINT, signal.SIGTERM):
            with self.subTest(signal=signum):
                await self.cli_shutdown(signum)

    async def cli_shutdown(self, signum):
        process = await asyncio.create_subprocess_exec(
            sys.executable, "-m", "finderlab", "web", "--listen-port", "0",
            "--data-dir", str(self.root / "cli-data"),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        try:
            line = await asyncio.wait_for(process.stdout.readline(), 5)
            self.assertTrue(line.startswith(b"Open http://127.0.0.1:"), line)
            process.send_signal(signum)
            _, errors = await asyncio.wait_for(process.communicate(), 5)
            self.assertEqual(process.returncode, 0, errors.decode())
            self.assertNotIn(b"Traceback", errors)
            self.assertEqual(list((self.root / "cli-data").glob("captures/*")), [])
        finally:
            if process.returncode is None:
                process.kill()
                await process.communicate()

    async def test_help_excerpt_is_cleared_for_slice_but_raw_history_is_preserved(self):
        state = Workbench.empty()
        capture = WebCapture(self.root / "excerpt-captures", "slice", state=state)
        try:
            capture.event("slicer_command", stage="help", argv=["fake-orca", "--help"])
            capture.event("slicer_output", stage="help", stream="stdout", text="help text", data_hex=b"help text".hex())
            self.assertEqual(state["slicer_log"], "help text")
            capture.event("slicer_command", stage="slice", argv=["fake-orca", "--slice", "0"])
            self.assertEqual(state["slicer_stage"], "slice")
            self.assertEqual(state["slicer_log"], "")
            records = [json.loads(line) for line in (capture.path / "events.jsonl").read_text().splitlines()]
            self.assertTrue(any(e.get("text") == "help text" for e in records))
        finally:
            capture.close()

    async def test_passive_status_endpoint_only_reads_configured_recording(self):
        from finderlab.capture import Capture
        from test_passive_status import TEMP, STATUS, PROGRESS
        folder = self.root / "status-captures"
        capture = Capture(folder, "proxy", metadata={"config": {"host": "127.0.0.1", "port": self.config.client.port,
                          "target_host": "192.0.2.10", "target_port": 8899}})
        capture.session().data("server_to_client", TEMP + STATUS + PROGRESS)
        capture.close()
        self.server.config = replace(self.config, status_capture=folder)
        with patch("finderlab.web.FinderClient") as client:
            code, raw = await self.request("GET", "/api/printer-status")
            self.assertEqual(code, 200)
            observed = json.loads(raw)
            self.assertTrue(observed["passive"])
            self.assertEqual(observed["samples"]["M105"]["values"]["nozzle"], 220)
            self.assertEqual(observed["samples"]["M27"]["values"]["percent"], 100)
            self.assertEqual((await self.request("GET", "/api/printer-status?target=other"))[0], 400)
            client.assert_not_called()
        self.assertEqual(self.mock.files, {})

    async def test_static_config_and_state_do_not_contact_target(self):
        with patch("finderlab.web.FinderClient") as client:
            for path in ("/", "/app.js", "/style.css", "/api/config", "/api/state", "/api/printer-status"):
                code, content = await self.request("GET", path)
                self.assertEqual(code, 200)
                self.assertTrue(content)
            client.assert_not_called()
        code, data = await self.request("GET", "/api/config")
        self.assertEqual(json.loads(data)["token"], self.server.token)
        self.assertFalse(json.loads(data)["job_controls_enabled"])
        self.assertEqual(self.mock.files, {})

    async def test_host_origin_token_and_parser_boundaries(self):
        for headers in ({"Host": "evil.invalid"}, {"Origin": "http://evil.invalid"}, {"X-Finder-Token": "wrong"}):
            code, _ = await self.request("POST", "/api/discard", b'{"confirm":true}', headers)
            self.assertEqual(code, 403)
        for headers in ({"Transfer-Encoding": "chunked"}, {"Content-Length": "-1"},
                        {"Content-Length": "9" * 20}, {"host": self.server.authority}, {"Expect": "100-continue"}):
            code, _ = await self.request("POST", "/api/discard", b"{}", headers)
            self.assertIn(code, (400, 411))
        code, _ = await self.post("/api/save", {"confirm": True, "host": "192.0.2.1"})
        self.assertEqual(code, 400)
        code, _ = await self.request("GET", "/../../AGENTS.md")
        self.assertEqual(code, 404)
        code, _ = await self.request("OPTIONS", "/api/state")
        self.assertEqual(code, 405)
        code, _ = await self.request("POST", "/api/save", b"{" * 2049)
        self.assertEqual(code, 413)
        self.assertEqual(self.mock.files, {})

    async def test_upload_requires_explicit_save_and_never_starts(self):
        payload = b"ok\r\n~M29\0" + bytes(range(256)) * 20
        code, _ = await self.file("sample.gx", payload)
        self.assertEqual(code, 200)
        self.assertEqual(self.mock.files, {})
        code, artifact = await self.request("GET", "/api/artifact")
        self.assertEqual((code, artifact), (200, payload))
        code, _ = await self.post("/api/save", {"remote_name": "sample.gx"})
        self.assertEqual(code, 400)
        code, _ = await self.post("/api/save", {"confirm": True, "remote_name": "sample.gx"})
        self.assertEqual(code, 200)
        state = await self.finish()
        self.assertTrue(state["saved"])
        self.assertEqual(state["sha256"], hashlib.sha256(payload).hexdigest())
        self.assertEqual(self.mock.files["sample.gx"], payload)
        self.assertIsNone(self.mock.active_file)
        manifest = json.loads((Path(state["capture"]) / "manifest.json").read_text())
        self.assertTrue(manifest["metadata"]["upload_confirmed"])
        self.assertFalse(manifest["metadata"]["start_requested"])
        self.assertTrue(manifest["complete"])
        raw = (Path(state["capture"]) / "sessions/s0001/client-to-server.bin").read_bytes()
        commands = []
        while raw:
            if raw.startswith(bytes.fromhex("5a5aa5a5")):
                raw = raw[4112:]
            else:
                command, raw = raw.split(b"\r\n", 1)
                commands.append(command.split()[0])
        self.assertEqual(commands, [b"~M601", b"~M115", b"~M119", b"~M28", b"~M29", b"~M602"])
        code, _ = await self.post("/api/save", {"confirm": True, "remote_name": "again.gx"})
        self.assertEqual(code, 409)

    async def test_receive_limits_early_eof_and_single_slot(self):
        for name in ("../escape.gx", "wrong.3mf", "bad%00.gx"):
            code, _ = await self.file(name)
            self.assertEqual(code, 400)
        for name, size in (("big.gx", PRINT_LIMIT+1), ("big.stl", MODEL_LIMIT+1), ("empty.gx", 0)):
            code, _ = await self.request("POST", "/api/file?name=" + name, b"",
                       {"Content-Type": "application/octet-stream", "Content-Length": str(size)})
            self.assertEqual(code, 413)
        code, _ = await self.request("POST", "/api/file?name=partial.gx", b"short",
                   {"Content-Type": "application/octet-stream", "Content-Length": "100"}, early_eof=True)
        self.assertEqual(code, 400)
        self.assertFalse(self.server.work.state["busy"])
        self.assertEqual(self.server.work.state["phase"], "empty")
        self.assertEqual(list(self.server.work.folder.glob("file-*")), [])
        self.assertEqual((await self.file("one.gx"))[0], 200)
        self.assertEqual((await self.file("two.gx"))[0], 409)
        self.assertEqual((await self.post("/api/discard", {"confirm": True}))[0], 200)
        self.assertEqual((await self.file("two.gx"))[0], 200)

    async def test_disabled_upload_and_slicing_have_no_connection(self):
        self.server.work.config = replace(self.config, enable_upload=False)
        await self.file("print.gcode")
        with patch("finderlab.web.FinderClient") as client:
            self.assertEqual((await self.post("/api/save", {"confirm": True, "remote_name": "p.gcode"}))[0], 409)
            await self.post("/api/discard", {"confirm": True})
            await self.file("model.stl", b"solid synthetic\nendsolid synthetic")
            self.assertEqual((await self.post("/api/slice", {"confirm": True}))[0], 409)
            client.assert_not_called()

    async def test_unknown_save_is_locked_against_blind_retry(self):
        await self.file("print.gx")
        with patch("finderlab.web.FinderClient", side_effect=OSError("synthetic lost connection")) as client:
            await self.post("/api/save", {"confirm": True, "remote_name": "p.gx"})
            state = await self.finish()
            self.assertEqual(state["phase"], "unknown")
            self.assertFalse(state["saved"])
            self.assertEqual((await self.post("/api/save", {"confirm": True, "remote_name": "p.gx"}))[0], 409)
            self.assertEqual(client.call_count, 1)

    async def save_for_controls(self):
        self.server.work.config = replace(self.config, enable_job_controls=True)
        self.server.config = self.server.work.config
        await self.file("source.gx")
        await self.post("/api/save", {"confirm": True, "remote_name": "exact saved.gx"})
        return await self.finish()

    async def test_job_controls_disabled_and_confirmation_required(self):
        with patch("finderlab.web.FinderClient") as client:
            for path in ("/api/start", "/api/stop"):
                self.assertEqual((await self.post(path, {"confirm": True}))[0], 409)
            self.server.work.config = replace(self.config, enable_job_controls=True)
            for path in ("/api/start", "/api/stop"):
                for data in ({}, {"confirm": "true"}, {"confirm": True, "host": "192.0.2.1"}):
                    self.assertEqual((await self.post(path, data))[0], 400)
            self.assertEqual((await self.post("/api/start", {"confirm": True}))[0], 409)
            client.assert_not_called()

    async def test_explicit_start_exact_saved_file_then_separate_cancel(self):
        saved = await self.save_for_controls()
        self.assertIsNone(self.mock.active_file)
        save_id = saved["save_id"]
        self.assertEqual((await self.post("/api/start", {"confirm": True, "save_id": "stale"}))[0], 409)
        self.assertEqual((await self.post("/api/start", {"confirm": True, "save_id": save_id, "remote_name": "other.gx"}))[0], 400)
        self.assertEqual((await self.post("/api/start", {"confirm": True, "save_id": save_id}))[0], 200)
        state = await self.finish()
        self.assertEqual(self.mock.active_file, "exact saved.gx")
        self.assertEqual(state["job_result"], "start_acknowledged")
        capture = Path(state["capture"])
        manifest = json.loads((capture / "manifest.json").read_text())
        self.assertTrue(manifest["metadata"]["start_requested"])
        self.assertTrue(manifest["metadata"]["start_acknowledged"])
        commands = (capture / "sessions/s0001/client-to-server.bin").read_bytes().splitlines()
        self.assertEqual(commands, [b"~M601 S1", b"~M115", b"~M119", b"~M23 0:/user/exact saved.gx", b"~M602"])
        self.assertEqual((await self.post("/api/start", {"confirm": True, "save_id": save_id}))[0], 409)
        await self.post("/api/stop", {"confirm": True})
        state = await self.finish()
        self.assertIsNone(self.mock.active_file)
        self.assertEqual(state["job_result"], "cancel_acknowledged")
        commands = (Path(state["capture"]) / "sessions/s0001/client-to-server.bin").read_bytes().splitlines()
        self.assertEqual(commands, [b"~M601 S1", b"~M115", b"~M26", b"~M602"])
        self.assertTrue(state["saved"], "Cancel must not erase the confirmed save fact")

    async def test_start_rechecks_ready_without_cancelling_an_external_job(self):
        saved = await self.save_for_controls()
        async with FinderClient(self.config.client) as external:
            await external.start("exact saved.gx", confirm=True)
        await self.post("/api/start", {"confirm": True, "save_id": saved["save_id"]})
        state = await self.finish()
        self.assertEqual(state["phase"], "unknown")
        self.assertTrue(state["saved"])
        self.assertEqual(self.mock.active_file, "exact saved.gx")
        commands = (Path(state["capture"]) / "sessions/s0001/client-to-server.bin").read_bytes().splitlines()
        self.assertEqual(commands, [b"~M601 S1", b"~M115", b"~M119", b"~M602"])

    async def test_unknown_start_preserves_save_and_prevents_repeat(self):
        from finderlab.client import ResultUnknown
        from unittest.mock import AsyncMock
        saved = await self.save_for_controls()
        with patch("finderlab.web.FinderClient.start", new=AsyncMock(side_effect=ResultUnknown("synthetic lost start reply"))) as start:
            await self.post("/api/start", {"confirm": True, "save_id": saved["save_id"]})
            state = await self.finish()
            self.assertEqual(state["job_result"], "start_unknown")
            self.assertTrue(state["saved"])
            self.assertEqual((await self.post("/api/start", {"confirm": True, "save_id": saved["save_id"]}))[0], 409)
            self.assertEqual(start.await_count, 1)

    async def test_unknown_cancel_is_not_retried_by_status_reads(self):
        from finderlab.client import ResultUnknown
        from unittest.mock import AsyncMock
        self.server.work.config = replace(self.config, enable_upload=False, enable_job_controls=True)
        with patch("finderlab.web.FinderClient.stop", new=AsyncMock(side_effect=ResultUnknown("synthetic lost cancel reply"))) as stop:
            await self.post("/api/stop", {"confirm": True})
            state = await self.finish()
            self.assertEqual(state["phase"], "unknown")
            self.assertEqual(state["job_result"], "stop_unknown")
            await self.request("GET", "/api/state")
            await self.request("GET", "/api/state")
            self.assertEqual(stop.await_count, 1)

    async def test_cancel_available_without_local_file_and_discard_clears_start_reference(self):
        saved = await self.save_for_controls()
        save_id = saved["save_id"]
        await self.post("/api/discard", {"confirm": True})
        self.assertEqual((await self.post("/api/start", {"confirm": True, "save_id": save_id}))[0], 409)
        self.assertEqual((await self.post("/api/stop", {"confirm": True}))[0], 200)
        self.assertEqual((await self.finish())["job_result"], "cancel_acknowledged")

    async def test_recording_failure_closes_without_saving_or_retrying(self):
        await self.file("quota.gx")
        with patch("finderlab.web.CAPTURE_LIMIT", 128):
            await self.post("/api/save", {"confirm": True, "remote_name": "quota.gx"})
            state = await self.finish()
        self.assertFalse(state["saved"])
        self.assertFalse(state["busy"])
        self.assertEqual(state["phase"], "unknown")
        self.assertEqual(self.mock.files, {})
        manifest = json.loads((Path(state["capture"]) / "manifest.json").read_text())
        self.assertFalse(manifest["complete"])
        self.assertEqual((await self.post("/api/save", {"confirm": True, "remote_name": "quota.gx"}))[0], 409)

    async def test_owned_dummy_overrides_target_and_supports_confirmed_virtual_job(self):
        cfg = WebConfig(port=0, data_dir=self.root / "owned-dummy",
                        client=ClientConfig(host="192.0.2.1", allow_hardware=True),
                        enable_job_controls=True, status_capture=self.root / "must-not-observe-hardware")
        previous = self.server
        async with serve_workbench(cfg, dummy=True) as owned:
            self.server = owned
            address = owned.owned_dummy.address
            try:
                code, content = await self.request("GET", "/api/config")
                capabilities = json.loads(content)
                self.assertTrue(capabilities["owned_dummy"])
                self.assertFalse(capabilities["passive_status_enabled"])
                self.assertTrue(capabilities["sliced_upload_enabled"])
                self.assertTrue(capabilities["job_controls_enabled"])
                self.assertEqual(owned.config.client.host, "127.0.0.1")
                self.assertFalse(owned.config.client.allow_hardware)
                payload = b"; synthetic dummy save only\x00~M29"
                await self.file("virtual.gcode", payload)
                await self.post("/api/save", {"confirm": True, "remote_name": "virtual.gcode"})
                result = await self.finish()
                self.assertTrue(result["saved"])
                self.assertEqual(owned.owned_dummy.files["virtual.gcode"], payload)
                self.assertIsNone(owned.owned_dummy.active_file)
                manifest = json.loads((Path(result["capture"]) / "manifest.json").read_text())
                self.assertEqual(manifest["metadata"]["target_kind"], "owned_dummy")
                self.assertIn("emulated", manifest["model"])
                self.assertEqual((await self.post("/api/start", {"save_id": result["save_id"]}))[0], 400)
                self.assertIsNone(owned.owned_dummy.active_file)
                self.assertEqual((await self.post("/api/start", {"confirm": True, "save_id": result["save_id"]}))[0], 200)
                result = await self.finish()
                self.assertEqual(result["job_result"], "start_acknowledged")
                self.assertEqual(owned.owned_dummy.active_file, "virtual.gcode")
                self.assertEqual((await self.post("/api/stop", {"confirm": False}))[0], 400)
                self.assertEqual(owned.owned_dummy.active_file, "virtual.gcode")
                self.assertEqual((await self.post("/api/stop", {"confirm": True}))[0], 200)
                self.assertEqual((await self.finish())["job_result"], "cancel_acknowledged")
                self.assertIsNone(owned.owned_dummy.active_file)
            finally:
                self.server = previous
        with self.assertRaises(OSError):
            await asyncio.open_connection(*address)

    async def test_storage_quota_and_workspace_lock(self):
        with patch("finderlab.web.STORAGE_LIMIT", 100):
            self.assertEqual((await self.file("quota.gx"))[0], 507)
        other = WebServer(self.config)
        with self.assertRaises(OSError):
            await other.__aenter__()
        self.assertFalse(self.server.work.state["busy"])

    def configure_fake_orca(self, behavior="ok"):
        fake = self.root / "fake-orca"
        fake.write_text(f"#!{sys.executable}\nBEHAVIOR={behavior!r}\nPAYLOAD={PAYLOAD!r}\n" + FAKE)
        fake.chmod(0o700)
        settings = {
            "machine": {"gcode_flavor": "sailfish", "printable_area": ["0x0", "10x0", "10x10"],
                        "printable_height": "10", "use_relative_e_distances": "0",
                        "machine_start_gcode": "; synthetic", "machine_end_gcode": "; synthetic"},
            "process": {"layer_height": "0.2", "initial_layer_print_height": "0.2", "travel_speed": "10", "travel_speed_z": "1"},
            "filament": {"nozzle_temperature": ["0"], "nozzle_temperature_initial_layer": ["0"]}}
        profiles = {}
        for kind, values in settings.items():
            path = self.root / (kind + ".json")
            path.write_text(json.dumps({"type": kind, **values}))
            profiles[kind] = path
        cfg = SliceConfig(**profiles, orca=str(fake), timeout=3)
        self.server.work.config = replace(self.config, slicing=cfg)

    async def test_invalid_quality_settings_rejected_before_native_or_printer_action(self):
        self.configure_fake_orca()
        await self.file("model.stl", b"solid synthetic\nendsolid synthetic")
        with patch("finderlab.web.slice_model") as slicer, patch("finderlab.web.FinderClient") as client:
            for settings in ({"brim_width": 100}, {"layer_height": "0.2"}, {"brim": "unknown"},
                             {"layer_height": True}, {"layer_height": 10**1000}, {"post_process": "untrusted"}, []):
                code, _ = await self.post("/api/slice", {"confirm": True, "settings": settings})
                self.assertEqual(code, 400)
            self.assertEqual(self.server.work.state["phase"], "model_ready")
            self.assertFalse(self.server.work.state["busy"])
            slicer.assert_not_called(); client.assert_not_called()
            self.assertEqual((await self.post("/api/save", {"confirm": True, "remote_name": "test.gcode", "settings": {}}))[0], 400)

    async def test_web_quality_settings_recorded_and_locked_to_artifact(self):
        self.configure_fake_orca()
        await self.file("model.stl", b"solid synthetic\nendsolid synthetic")
        settings = {"layer_height": 0.12, "brim": "outer", "brim_width": 5}
        with patch("finderlab.web.FinderClient") as client:
            code, _ = await self.post("/api/slice", {"confirm": True, "settings": settings})
            self.assertEqual(code, 200)
            state = await self.finish()
            client.assert_not_called()
        self.assertEqual(state["slice_settings"], settings)
        self.assertEqual(state["effective_quality"]["layer_height"], "0.12")
        self.assertEqual(state["effective_quality"]["brim_width"], "5")
        self.assertEqual(state["effective_quality"]["initial_layer_print_height"], "0.2")
        manifest = json.loads((Path(state["capture"]) / "manifest.json").read_text())
        self.assertEqual(manifest["metadata"]["slice_settings"], settings)
        self.assertEqual((await self.post("/api/slice", {"confirm": True, "settings": {"brim": "off"}}))[0], 409)
        self.assertEqual(self.server.work.state["slice_settings"], settings)
        await self.post("/api/discard", {"confirm": True})
        self.assertIsNone(self.server.work.state["slice_settings"])

    async def test_fake_slice_then_separate_review_and_save_gate(self):
        self.configure_fake_orca()
        await self.file("model.stl", b"solid synthetic\nendsolid synthetic")
        with patch("finderlab.web.FinderClient") as client:
            self.assertEqual((await self.post("/api/slice", {"confirm": True}))[0], 200)
            state = await self.finish()
            client.assert_not_called()
        self.assertEqual(state["phase"], "review")
        self.assertTrue(state["sliced"])
        self.assertEqual(state["suggested_name"], "model.gcode")
        self.assertEqual(self.server.work.artifact.name, "model.gcode")
        self.assertEqual((await self.request("GET", "/api/artifact"))[1], PAYLOAD)
        self.assertEqual((await self.post("/api/save", {"confirm": True, "remote_name": "sliced.gcode"}))[0], 409)
        self.server.work.config = replace(self.server.work.config, allow_sliced_upload=True)
        self.assertEqual((await self.post("/api/save", {"confirm": True, "remote_name": "wrong.gx"}))[0], 400)
        await self.post("/api/save", {"confirm": True, "remote_name": "sliced.gcode"})
        self.assertTrue((await self.finish())["saved"])
        self.assertEqual(self.mock.files["sliced.gcode"], PAYLOAD)
        self.assertIsNone(self.mock.active_file)

    async def test_busy_slot_and_shutdown_cancel_local_work_only(self):
        self.configure_fake_orca()
        await self.file("model.stl", b"solid synthetic\nendsolid synthetic")
        entered = asyncio.Event()
        async def wait_for_shutdown(*args, **kwargs):
            entered.set()
            await asyncio.Event().wait()
        with patch("finderlab.web.slice_model", side_effect=wait_for_shutdown), patch("finderlab.web.FinderClient") as client:
            await self.post("/api/slice", {"confirm": True})
            await asyncio.wait_for(entered.wait(), 2)
            self.assertEqual((await self.post("/api/discard", {"confirm": True}))[0], 409)
            self.assertEqual((await self.file("other.gx"))[0], 409)
            self.assertEqual((await self.post("/api/slice", {"confirm": True}))[0], 409)
            self.assertEqual((await self.post("/api/save", {"confirm": True, "remote_name": "bad.gx"}))[0], 409)
            self.assertEqual((await self.request("GET", "/api/artifact"))[0], 409)
            await self.server.__aexit__(None, None, None)
            client.assert_not_called()
        self.assertFalse(self.server.work.state["busy"])
        self.assertEqual(self.server.work.state["phase"], "failed")
        manifest = json.loads((Path(self.server.work.state["capture"]) / "manifest.json").read_text())
        self.assertTrue(manifest["complete"])
        self.assertEqual(manifest["sessions"], [])

    async def test_failed_fake_slice_never_connects_or_publishes(self):
        self.configure_fake_orca("fail")
        await self.file("model.stl", b"solid synthetic\nendsolid synthetic")
        with patch("finderlab.web.FinderClient") as client:
            await self.post("/api/slice", {"confirm": True})
            state = await self.finish()
            client.assert_not_called()
        self.assertEqual(state["phase"], "failed")
        self.assertFalse(state["artifact"])
        self.assertIn("synthetic Orca error", state["slicer_log"])
        self.assertLessEqual(len(state["slicer_log"]), 4000)
        self.assertEqual((await self.request("GET", "/api/artifact"))[0], 404)
        self.assertEqual(self.mock.files, {})


class WebConfigTests(unittest.TestCase):
    def test_source_based_safe_filenames(self):
        self.assertEqual(suggested_name("WN_field_4x4_halfpans_lid.stl"), "WN_field_4x4_halfpans_lid.gcode")
        self.assertEqual(suggested_name("Räcke.stl"), "Racke.gcode")
        for source in ('...stl', '☃.stl', 'a";bad.stl', 'a' * 190 + '.stl'):
            result = suggested_name(source)
            self.assertLessEqual(len(result), 128)
            self.assertNotIn('..', result)
            self.assertNotIn('"', result)
            self.assertTrue(result.endswith('.gcode'))

    def test_loopback_only_and_fixed_limits(self):
        with self.assertRaises(ValueError): WebConfig(host="0.0.0.0")
        with self.assertRaises(ValueError): WebConfig(client=ClientConfig(max_file_size=100))
