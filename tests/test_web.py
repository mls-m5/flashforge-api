"""Standalone HTTP/UI contracts; ephemeral loopback only, fake Orca, no hardware."""

import asyncio
from contextlib import asynccontextmanager
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
        if path == "/api/model":
            base["X-Finder-Token"] = self.server.token
        if getattr(self, "authorization", None):
            base["Authorization"] = self.authorization
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
        self.last_headers = head
        return status, content

    async def post(self, path, data):
        return await self.request("POST", path, json.dumps(data).encode())

    async def file(self, name, data=b"; synthetic\x00ok\r\n~M29" * 500):
        return await self.request("POST", "/api/file?name=" + name, data,
                                  {"Content-Type": "application/octet-stream"})

    async def finish(self):
        await asyncio.wait_for(asyncio.shield(self.server.work.task), 5)
        return self.server.work.state

    async def test_active_polling_autostarts_then_yields_for_save_and_can_stop_without_cancel(self):
        from test_active_status import wait_until
        await self.server.__aexit__(None, None, None)
        self.server = await WebServer(replace(self.config, enable_monitor=True, auto_monitor=True)).__aenter__()
        monitor = self.server.work.monitor
        await wait_until(lambda: bool(monitor.samples))
        first_session = monitor.sample_session
        stamp = monitor.samples["M105"]["observed_utc"]
        await wait_until(lambda: monitor.samples["M105"]["observed_utc"] != stamp)
        self.assertEqual(monitor.sample_session, first_session, "polls reuse one firmware-gated session")
        from datetime import datetime
        self.assertGreaterEqual((datetime.fromisoformat(monitor.samples["M105"]["observed_utc"]) - datetime.fromisoformat(stamp)).total_seconds(), 1)
        status, content = await self.request("GET", "/api/printer-status")
        self.assertEqual(status, 200)
        self.assertTrue(json.loads(content)["monitor_running"])
        payload = b"; synthetic no physical G-code\n" * 600
        self.assertEqual((await self.file("sample.gcode", payload))[0], 200)
        self.assertEqual((await self.post("/api/save", {"confirm": True, "remote_name": "sample.gcode"}))[0], 200)
        state = await self.finish()
        self.assertTrue(state["saved"], state)
        self.assertEqual(self.mock.files["sample.gcode"], payload)
        await wait_until(lambda: monitor.sample_session != first_session)
        self.assertTrue(monitor.enabled)
        status, _ = await self.post("/api/monitor", {"enabled": False, "confirm": True})
        self.assertEqual(status, 200)
        await monitor.close()
        for path in self.server.work.folder.glob("captures/*/sessions/*/client-to-server.bin"):
            data = path.read_bytes()
            self.assertNotIn(b"~M23", data)
            self.assertNotIn(b"~M26", data)
        self.assertTrue(monitor.capture.closed)

    async def test_active_monitor_gate_confirmation_and_same_origin(self):
        self.assertEqual((await self.post("/api/monitor", {"enabled": True, "confirm": True}))[0], 409)
        await self.server.__aexit__(None, None, None)
        self.server = await WebServer(replace(self.config, enable_monitor=True)).__aenter__()
        for data in ({"enabled": 1, "confirm": True}, {"enabled": True}, {"enabled": True, "confirm": True, "host": "example.invalid"}):
            self.assertEqual((await self.post("/api/monitor", data))[0], 400)
        status, _ = await self.request("POST", "/api/monitor", b'{"enabled":true,"confirm":true}', {"Origin": "http://example.invalid"})
        self.assertEqual(status, 403)
        self.assertIsNone(self.server.work.monitor)
        self.assertEqual((await self.post("/api/monitor", {"enabled": True, "confirm": True}))[0], 200)
        self.assertEqual((await self.post("/api/monitor", {"enabled": True, "confirm": True}))[0], 409)

    async def test_uncertain_save_stops_monitor_instead_of_auto_reconnecting(self):
        from test_active_status import wait_until
        from unittest.mock import AsyncMock
        await self.server.__aexit__(None, None, None)
        self.server = await WebServer(replace(self.config, enable_monitor=True, auto_monitor=True)).__aenter__()
        monitor = self.server.work.monitor
        await wait_until(lambda: bool(monitor.samples))
        await self.file("sample.gcode")
        with patch("finderlab.web.FinderClient.upload", new=AsyncMock(side_effect=OSError("synthetic uncertain save"))):
            await self.post("/api/save", {"confirm": True, "remote_name": "sample.gcode"})
            state = await self.finish()
        self.assertEqual(state["phase"], "unknown")
        await monitor.close()
        self.assertFalse(monitor.enabled)
        self.assertEqual(len(monitor.capture.sessions), 1)
        self.assertTrue(monitor.report()["stale"])

    async def test_foreground_recording_finalization_failure_stops_monitor(self):
        from test_active_status import wait_until
        await self.server.__aexit__(None, None, None)
        self.server = await WebServer(replace(self.config, enable_monitor=True, auto_monitor=True)).__aenter__()
        monitor = self.server.work.monitor
        await wait_until(lambda: bool(monitor.samples))
        await self.file("sample.gcode")
        original = WebCapture.close
        def fail_finalization(capture):
            original(capture)
            raise OSError("synthetic final manifest failure")
        with patch.object(WebCapture, "close", fail_finalization):
            await self.post("/api/save", {"confirm": True, "remote_name": "sample.gcode"})
            state = await self.finish()
        self.assertEqual(state["phase"], "unknown")
        self.assertTrue(state["saved"], "confirmed save fact survives logging failure")
        await monitor.close()
        self.assertFalse(monitor.enabled)
        self.assertEqual(len(monitor.capture.sessions), 1)

    async def test_auto_monitor_storage_failure_keeps_ui_available_without_connecting(self):
        from finderlab.web import WebError
        await self.server.__aexit__(None, None, None)
        with patch("finderlab.web.Workbench.capacity", side_effect=WebError(507, "synthetic full workspace")):
            self.server = await WebServer(replace(self.config, enable_monitor=True, auto_monitor=True)).__aenter__()
        self.assertFalse(self.server.work.monitor.enabled)
        self.assertIsNone(self.server.work.monitor.capture)
        status, content = await self.request("GET", "/api/printer-status")
        self.assertEqual(status, 200)
        self.assertIn("full workspace", json.loads(content)["message"])

    @asynccontextmanager
    async def owned_manual(self):
        previous = self.server
        try:
            async with serve_workbench(replace(self.config, data_dir=self.root / "manual-owned"), dummy=True) as owned:
                self.server = owned
                yield owned
        finally:
            self.server = previous

    async def manual(self, action, revision=0, **fields):
        return await self.post("/api/manual", {"confirm": True, "revision": revision, "action": action, **fields})

    async def test_manual_controls_stay_locked_for_configured_loopback_and_proxy(self):
        with patch("finderlab.web.FinderClient") as connect:
            code, content = await self.request("GET", "/api/manual-state")
            self.assertEqual(code, 200)
            self.assertFalse(json.loads(content)["enabled"])
            self.assertEqual((await self.manual("jog", axis="X", distance=1))[0], 409)
            self.assertEqual((await self.post("/api/manual", {"owned_dummy": True, "confirm": True}))[0], 409)
            self.assertEqual((await self.request("GET", "/manual.js"))[0], 200)
            connect.assert_not_called()
        self.assertEqual(list(self.server.work.folder.glob("captures/*")), [])

    async def test_owned_manual_intents_are_audited_without_sockets_or_file_slot_changes(self):
        async with self.owned_manual() as owned:
            before = dict(owned.work.state)
            with patch("finderlab.web.FinderClient") as connect, patch("finderlab.active_status.FinderClient") as monitor_connect:
                code, content = await self.manual("light", rgb=[136, 138, 133])
                self.assertEqual(code, 200)
                self.assertEqual(json.loads(content)["state"]["rgb"], [136, 138, 133])
                code, content = await self.manual("jog", revision=1, axis="X", distance=.1)
                self.assertEqual(code, 200)
                self.assertEqual(json.loads(content)["state"]["offsets_mm"]["X"], .1)
                await self.post("/api/discard", {"confirm": True})
                code, content = await self.request("GET", "/api/manual-state")
                self.assertEqual(json.loads(content)["state"]["revision"], 2, "discard does not zero counters")
                connect.assert_not_called(); monitor_connect.assert_not_called()
            self.assertEqual(owned.work.state, before)
            manifests = list(owned.work.folder.glob("captures/*/manifest.json"))
            self.assertEqual(len(manifests), 2)
            for file in manifests:
                capture = json.loads(file.read_text())
                self.assertTrue(capture["complete"])
                self.assertEqual(capture["mode"], "manual-virtual")
                self.assertFalse(capture["metadata"]["wire_commands_sent"])
                self.assertEqual(capture["sessions"], [])

    async def test_manual_revisions_prevent_concurrent_double_click_and_cold_extrusion(self):
        async with self.owned_manual():
            responses = await asyncio.gather(self.manual("jog", axis="X", distance=1), self.manual("jog", axis="X", distance=1))
            self.assertEqual(sorted(code for code, _ in responses), [200, 409])
            self.assertEqual((await self.manual("extrude", revision=1, distance=1))[0], 400)
            self.assertEqual((await self.manual("warm", revision=1, enabled=True))[0], 200)
            code, content = await self.manual("extrude", revision=2, distance=5)
            self.assertEqual(code, 200)
            self.assertEqual(json.loads(content)["state"]["extruded_mm"], 5)
            self.assertEqual(json.loads(content)["state"]["offsets_mm"]["X"], 1)

    async def test_manual_api_validation_busy_unknown_and_origin_guard(self):
        async with self.owned_manual() as owned:
            for fields in ({"action": "G1 X1000"}, {"action": "jog", "axis": "X", "distance": "1"},
                           {"action": "light", "rgb": [1, 2, 3], "target": "example.invalid"},
                           {"action": "jog", "axis": "Z", "distance": 5}):
                self.assertEqual((await self.post("/api/manual", {"revision": 0, "confirm": True, **fields}))[0], 400)
            code, _ = await self.request("POST", "/api/manual", b'{"confirm":true,"action":"light","rgb":[0,0,0],"revision":0}', {"Origin": "http://example.invalid"})
            self.assertEqual(code, 403)
            owned.work.state["busy"] = True
            self.assertEqual((await self.manual("light", rgb=[0, 0, 0]))[0], 409)
            owned.work.state.update(busy=False, phase="unknown")
            self.assertEqual((await self.manual("jog", axis="X", distance=1))[0], 409)
            self.assertEqual(owned.work.manual_controls.state["revision"], 0)

    async def test_manual_during_virtual_print_is_locked_until_explicit_cancel(self):
        async with self.owned_manual() as owned:
            await self.file("sample.gcode")
            await self.post("/api/save", {"confirm": True, "remote_name": "sample.gcode"})
            saved = await self.finish()
            await self.post("/api/start", {"confirm": True, "save_id": saved["save_id"]})
            await self.finish()
            self.assertIsNotNone(owned.owned_dummy.active_file)
            self.assertEqual((await self.manual("jog", axis="Z", distance=.1))[0], 409)
            self.assertIsNotNone(owned.owned_dummy.active_file, "rejected jog does not cancel the virtual print")
            await self.post("/api/stop", {"confirm": True})
            await self.finish()
            self.assertEqual((await self.manual("jog", axis="Z", distance=.1))[0], 200)

    async def test_manual_recording_failure_and_storage_quota_do_not_commit_counter(self):
        from finderlab.web import WebError
        from finderlab.capture import Capture
        async with self.owned_manual() as owned:
            original = Capture.event
            def fail_event(capture, kind, *args, **kwargs):
                if kind == "manual_virtual_intent": raise OSError("synthetic log failure")
                return original(capture, kind, *args, **kwargs)
            with patch.object(Capture, "event", fail_event):
                self.assertEqual((await self.manual("jog", axis="X", distance=1))[0], 500)
            self.assertEqual(owned.work.manual_controls.state["revision"], 0)
            close = Capture.close
            def fail_finalization(capture):
                close(capture)
                raise OSError("synthetic final manifest failure")
            with patch.object(Capture, "close", fail_finalization):
                self.assertEqual((await self.manual("jog", axis="Y", distance=1))[0], 500)
            self.assertEqual(owned.work.manual_controls.state["revision"], 0)
            with patch.object(owned.work, "capacity", side_effect=WebError(507, "synthetic full storage")):
                self.assertEqual((await self.manual("light", rgb=[255, 255, 255]))[0], 507)
            self.assertEqual(owned.work.manual_controls.state["revision"], 0)

    async def lan_server(self):
        import base64
        await self.server.__aexit__(None, None, None)
        # Authenticated LAN mode exercised on ephemeral LOOPBACK only, never an actual LAN interface.
        self.server = await WebServer(replace(self.config, lan=True, enable_job_controls=True, enable_monitor=True)).__aenter__()
        self.authorization = "Basic " + base64.b64encode(("finder:" + self.server.access.password).encode()).decode()

    async def test_lan_auth_guards_all_assets_reads_and_mutations_before_side_effects(self):
        await self.lan_server()
        with patch("finderlab.web.FinderClient") as connect:
            for path in ("/", "/app.js", "/manual.js", "/style.css", "/preview.js", "/toolpath-worker.js",
                         "/toolpath-view.js", "/vendor/three/three.module.min.js", "/vendor/three/OrbitControls.js",
                         "/vendor/three/LICENSE", "/model-preview.js", "/model-worker.js", "/model-transform.js", "/plate-preview.js", "/api/model", "/api/config", "/api/state",
                         "/api/printer-status", "/api/manual-state", "/api/artifact", "/api/gx-thumbnail"):
                code, body = await self.request("GET", path, headers={"Authorization": ""})
                self.assertEqual(code, 401, path)
                self.assertIn(b'WWW-Authenticate: Basic realm="Finder workbench"', self.last_headers)
                self.assertNotIn(self.server.token.encode(), body)
            for path in ("/api/stop", "/api/start", "/api/slice", "/api/save", "/api/discard", "/api/monitor", "/api/manual"):
                code, _ = await self.request("POST", path, b'{"confirm":true}', {"Authorization": "Basic invalid"})
                self.assertEqual(code, 401, path)
            self.assertEqual((await self.request("POST", "/api/file?name=test.gx", b"bytes",
                              {"Authorization": "", "Content-Type": "application/octet-stream"}))[0], 401)
            connect.assert_not_called()
        self.assertEqual(self.server.work.state["phase"], "empty")
        self.assertEqual(list(self.server.work.folder.glob("captures/*")), [])
        code, body = await self.request("GET", "/api/config")
        self.assertEqual(code, 200)
        self.assertTrue(json.loads(body)["lan_mode"])
        self.assertNotIn(self.server.access.password.encode(), body)
        self.assertNotIn(self.authorization.encode(), body)

    async def test_lan_password_does_not_bypass_origin_host_token_or_peer_filter(self):
        await self.lan_server()
        for headers in ({"Origin": "http://example.invalid"}, {"X-Finder-Token": "wrong"},
                        {"Host": "example.invalid"}):
            code, _ = await self.request("POST", "/api/stop", b'{"confirm":true}', headers)
            self.assertEqual(code, 403)
        with patch.object(self.server.access, "allows_peer", return_value=False):
            code, _ = await self.request("GET", "/api/config", headers={"X-Forwarded-For": "192.168.1.4"})
            self.assertEqual(code, 403)

    async def test_authenticated_shared_lan_workflow_saves_exact_file_and_starts_only_on_confirmation(self):
        await self.lan_server()
        from test_active_status import wait_until
        self.assertEqual((await self.post("/api/monitor", {"enabled": True, "confirm": True}))[0], 200)
        await wait_until(lambda: bool(self.server.work.monitor.samples))
        status = json.loads((await self.request("GET", "/api/printer-status"))[1])
        self.assertTrue(status["monitor_running"])
        payload = b"; synthetic local dummy only\n" * 200
        self.assertEqual((await self.file("shared.gcode", payload))[0], 200)
        # A second authenticated browser sees the same slot; GETs never send printer commands.
        self.assertEqual(json.loads((await self.request("GET", "/api/state"))[1])["name"], "shared.gcode")
        self.assertEqual((await self.post("/api/save", {"confirm": True, "remote_name": "shared.gcode"}))[0], 200)
        saved = await self.finish()
        self.assertTrue(saved["saved"])
        self.assertIsNone(self.mock.active_file)
        self.assertEqual(self.mock.files["shared.gcode"], payload)
        self.assertEqual((await self.request("GET", "/api/artifact"))[1], payload)
        self.assertEqual((await self.post("/api/start", {"confirm": True, "save_id": "stale"}))[0], 409)
        self.assertEqual((await self.post("/api/start", {"confirm": True, "save_id": saved["save_id"]}))[0], 200)
        await self.finish()
        self.assertEqual(self.mock.active_file, "shared.gcode")
        for p in self.server.work.folder.glob("captures/*/manifest.json"):
            self.assertNotIn(self.server.access.password, p.read_text())
        self.assertEqual((await self.post("/api/stop", {"confirm": True}))[0], 200)
        await self.finish()
        self.assertIsNone(self.mock.active_file)

    async def test_authenticated_lan_slice_is_offline_and_still_requires_separate_save(self):
        await self.lan_server()
        self.configure_fake_orca()
        self.assertTrue(self.server.config.lan)
        self.assertEqual((await self.file("shared.stl", b"solid synthetic\nendsolid synthetic"))[0], 200)
        with patch("finderlab.web.FinderClient") as connect:
            self.assertEqual((await self.post("/api/slice", {"confirm": True}))[0], 200)
            state = await self.finish()
            connect.assert_not_called()
        self.assertTrue(state["sliced"])
        self.assertFalse(state["saved"])
        self.assertIsNone(self.mock.active_file)
        self.assertEqual((await self.request("GET", "/api/artifact"))[1], PAYLOAD)

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

    async def test_storage_rejection_explains_reservation_and_monitor_stop_recovers(self):
        from types import SimpleNamespace
        from finderlab.web import WebError
        work=self.server.work
        total=sum(p.stat().st_size for p in work.folder.rglob('*') if p.is_file())
        monitor=SimpleNamespace(max_bytes=1000,capture=SimpleNamespace(closed=False,written=100))
        try:
            work.monitor=monitor
            with patch('finderlab.web.STORAGE_LIMIT',total+20):
                with self.assertRaises(WebError) as ctx:work.capacity(10)
                self.assertEqual(ctx.exception.status,507)
                self.assertIn('Operation was not started',str(ctx.exception))
                self.assertIn('Stop status polling',str(ctx.exception))
                self.assertIn('not print cancel',str(ctx.exception))
                monitor.capture.closed=True
                work.capacity(10)
        finally:work.monitor=None

    async def test_add_remove_multiple_stl_and_failed_append_preserves_existing_plate(self):
        from test_model_transform import ASCII
        await self.file('first.stl',ASCII);old=self.server.work.state['source_id']
        self.assertEqual((await self.file('second.stl',ASCII))[0],200)
        state=self.server.work.state;self.assertEqual(len(state['models']),2);self.assertNotEqual(state['source_id'],old)
        ids=[m['id'] for m in state['models']]
        for identifier in ids:
            code,body=await self.request('GET','/api/model?model='+identifier,headers={'X-Finder-Token':self.server.token})
            self.assertEqual((code,body),(200,ASCII))
        count=len(state['models'])
        code,_=await self.request('POST','/api/file?name=partial.stl',b'short',{'Content-Type':'application/octet-stream','Content-Length':'100'},early_eof=True)
        self.assertEqual(code,400);self.assertEqual(len(state['models']),count);self.assertFalse(state['busy'])
        self.assertEqual((await self.post('/api/model-remove',{'confirm':True,'source_id':old,'model_id':ids[0]}))[0],409)
        token=state['source_id']
        self.assertEqual((await self.post('/api/model-remove',{'confirm':True,'source_id':token,'model_id':ids[0]}))[0],200)
        self.assertEqual(len(state['models']),1);self.assertEqual(state['name'],'second.stl')
        self.assertNotEqual(state['source_id'],token)
        self.assertEqual((await self.request('GET','/api/model'))[1],ASCII)
        self.assertEqual((await self.file('more.gx'))[0],409)

    async def test_plate_slice_snapshot_and_gx_cover_all_models_with_no_upload(self):
        from test_model_transform import ASCII,MACHINE
        from test_gx_generation import CODE,PROCESS,FILAMENT
        self.configure_fake_orca();config=self.server.work.config.slicing
        config.machine.write_text(json.dumps(json.loads(config.machine.read_bytes())|MACHINE))
        config.process.write_text(json.dumps(json.loads(config.process.read_bytes())|PROCESS|{'print_sequence':'by object'}))
        config.filament.write_text(json.dumps(json.loads(config.filament.read_bytes())|FILAMENT))
        fake=Path(config.orca);fake.write_text(fake.read_text().replace(f'PAYLOAD={PAYLOAD!r}',f'PAYLOAD={CODE!r}').replace('value("--arrange") == "1"','value("--arrange") == "0"').replace('name == "model.stl"','name == "placed.stl"'))
        fake.write_text(fake.read_text().replace('print("READY "', 'assert json.loads(pathlib.Path(settings[1]).read_text())["print_sequence"] == "by layer"\nprint("READY "'))
        await self.file('a.stl',ASCII);await self.file('b.stl',ASCII)
        state=self.server.work.state;layout=[dict(id=m['id'],transform={'x':x}) for m,x in zip(state['models'],(-20,20))]
        body={'confirm':True,'source_id':state['source_id'],'plate':layout}
        with patch('finderlab.web.FinderClient') as client:
            self.assertEqual((await self.post('/api/slice',{'confirm':True}))[0],400)
            self.assertEqual((await self.post('/api/slice',body|{'source_id':'old'}))[0],409)
            self.assertEqual((await self.post('/api/slice',body))[0],200);state=await self.finish()
            self.assertEqual(state['phase'],'review',state['error']);self.assertEqual(state['plate'][0]['transform']['x'],-20.)
            self.assertEqual(json.loads(config.process.read_bytes())['print_sequence'],'by object','original process remains unchanged')
            geometry=self.server.work.gx_geometry
            from finderlab.model_transform import read_stl
            self.assertEqual(len(read_stl(geometry['path'])),6)
            self.assertEqual((await self.file('too-late.stl',ASCII))[0],409)
            self.assertEqual((await self.post('/api/model-remove',{'confirm':True,'source_id':state['source_id'],'model_id':layout[0]['id']}))[0],409)
            await self.post('/api/gx',{'confirm':True,'source_id':state['source_id'],'artifact_sha256':state['sha256']});state=await self.finish()
            self.assertTrue(state['gx_generated'],state['error'])
            manifest=json.loads((Path(state['capture'])/'manifest.json').read_bytes())
            self.assertEqual(manifest['metadata']['gx_result']['triangles'],2)
            self.assertEqual(manifest['metadata']['gx_inputs']['model']['sha256'],geometry['sha256'])
            client.assert_not_called()

    async def test_receive_limits_early_eof_and_single_slot(self):
        for name in ("../escape.gx", "wrong.obj", "bad%00.gx"):
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

    async def combined_request(self):
        self.server.work.config = replace(self.config, enable_job_controls=True)
        await self.file('source.gx')
        state=self.server.work.state
        return {'confirm':True,'remote_name':'combined exact.gx','start_after_upload':True,
                'artifact_sha256':state['sha256'],'source_id':state['source_id']}

    async def test_combined_save_start_is_exact_fresh_and_separately_recorded(self):
        from finderlab.web import WebError
        data=await self.combined_request()
        original=WebCapture.close; busy=[]
        def close(capture):
            original(capture)
            if capture.manifest['metadata']['operation']=='save':
                busy.append(self.server.work.state['busy'])
                with self.assertRaises(WebError):self.server.work.discard()
        with patch.object(WebCapture,'close',close):
            self.assertEqual((await self.post('/api/save',data))[0],200)
            state=await self.finish()
        self.assertEqual(busy,[True]);self.assertTrue(state['saved']);self.assertTrue(state['start_attempted'])
        self.assertEqual(self.mock.active_file,'combined exact.gx');self.assertEqual(state['job_result'],'start_acknowledged')
        self.assertNotEqual(state['save_capture'],state['start_capture'])
        saved=json.loads((Path(state['save_capture'])/'manifest.json').read_bytes())
        started=json.loads((Path(state['start_capture'])/'manifest.json').read_bytes())
        self.assertTrue(saved['complete']);self.assertTrue(saved['metadata']['start_after_upload'])
        self.assertEqual(saved['metadata']['save_id'],started['metadata']['save_id'])
        raw=(Path(state['start_capture'])/'sessions/s0001/client-to-server.bin').read_bytes().splitlines()
        self.assertEqual(raw,[b'~M601 S1',b'~M115',b'~M119',b'~M23 0:/user/combined exact.gx',b'~M602'])
        self.assertEqual((await self.post('/api/save',data))[0],409)
        self.assertEqual((await self.post('/api/start',{'confirm':True,'save_id':state['save_id']}))[0],409)

    async def test_combined_capability_type_and_stale_artifact_gates_before_connect(self):
        data=await self.combined_request()
        with patch('finderlab.web.FinderClient') as client:
            for key,value,code in [('start_after_upload','true',400),('artifact_sha256','old',409),('source_id','old',409)]:
                self.assertEqual((await self.post('/api/save',data|{key:value}))[0],code)
            missing=data.copy();missing.pop('artifact_sha256')
            self.assertEqual((await self.post('/api/save',missing))[0],409)
            self.server.work.config=replace(self.config,enable_job_controls=False)
            self.assertEqual((await self.post('/api/save',data))[0],409)
            client.assert_not_called()

    async def test_combined_failed_save_never_starts(self):
        from unittest.mock import AsyncMock
        from finderlab.client import ResultUnknown
        data=await self.combined_request()
        with patch('finderlab.web.FinderClient.upload',new=AsyncMock(side_effect=ResultUnknown('lost M29'))),patch('finderlab.web.FinderClient.start',new=AsyncMock()) as start:
            await self.post('/api/save',data);state=await self.finish()
            start.assert_not_awaited()
        self.assertFalse(state['saved']);self.assertEqual(state['job_result'],'start_not_sent')
        self.assertFalse(state['start_attempted']);self.assertEqual(state['phase'],'unknown')

    async def test_combined_changed_artifact_bytes_cannot_trigger_start(self):
        from unittest.mock import AsyncMock
        data=await self.combined_request();upload=FinderClient.upload
        async def mutate(client,path,**kwargs):
            Path(path).write_bytes(b'; changed before upload\n')
            return await upload(client,path,**kwargs)
        with patch('finderlab.web.FinderClient.upload',mutate),patch('finderlab.web.FinderClient.start',new=AsyncMock()) as start:
            await self.post('/api/save',data);state=await self.finish();start.assert_not_awaited()
        self.assertTrue(state['saved']);self.assertEqual(state['phase'],'unknown');self.assertEqual(state['job_result'],'start_not_sent')

    async def test_combined_release_or_save_finalization_failure_blocks_start(self):
        from unittest.mock import AsyncMock
        data=await self.combined_request()
        original=FinderClient.close
        async def fail_release(client):
            await original(client);client.cleanup_error='synthetic release failure'
        with patch('finderlab.web.FinderClient.close',fail_release),patch('finderlab.web.FinderClient.start',new=AsyncMock()) as start:
            await self.post('/api/save',data);state=await self.finish();start.assert_not_awaited()
        self.assertTrue(state['saved']);self.assertEqual(state['job_result'],'start_not_sent');self.assertIsNone(self.mock.active_file)
        await self.post('/api/discard',{'confirm':True})
        data=await self.combined_request();close=WebCapture.close
        def fail_capture(capture):close(capture);raise OSError('save record finalization failure')
        with patch.object(WebCapture,'close',fail_capture),patch('finderlab.web.FinderClient.start',new=AsyncMock()) as start:
            await self.post('/api/save',data);state=await self.finish();start.assert_not_awaited()
        self.assertTrue(state['saved']);self.assertEqual(state['phase'],'unknown');self.assertEqual(state['job_result'],'start_not_sent')

    async def test_combined_fresh_not_ready_and_unknown_start_never_retry_or_cancel(self):
        data=await self.combined_request();close=WebCapture.close
        def external_job(capture):
            close(capture)
            if capture.manifest['metadata']['operation']=='save':
                self.mock._files['external.gx']=b'x';self.mock._active_file='external.gx'
        with patch.object(WebCapture,'close',external_job):
            await self.post('/api/save',data);state=await self.finish()
        raw=(Path(state['start_capture'])/'sessions/s0001/client-to-server.bin').read_bytes()
        self.assertNotIn(b'~M23',raw);self.assertNotIn(b'~M26',raw)
        self.assertEqual(self.mock.active_file,'external.gx');self.assertTrue(state['saved']);self.assertTrue(state['start_attempted'])
        self.mock._active_file=None
        await self.post('/api/discard',{'confirm':True});data=await self.combined_request()
        from unittest.mock import AsyncMock
        from finderlab.client import ResultUnknown
        with patch('finderlab.web.FinderClient.start',new=AsyncMock(side_effect=ResultUnknown('lost start ACK'))) as start:
            await self.post('/api/save',data);state=await self.finish()
            await self.request('GET','/api/state');await self.request('GET','/api/state')
            self.assertEqual(start.await_count,1)
        self.assertTrue(state['saved']);self.assertEqual(state['job_result'],'start_unknown')
        self.assertEqual((await self.post('/api/start',{'confirm':True,'save_id':state['save_id']}))[0],409)

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
                             {"layer_height": True}, {"layer_height": 10**1000}, {"post_process": "untrusted"}, [],
                             {"xy_hole_compensation": "0.2"}, {"xy_hole_compensation": True},
                             {"xy_hole_compensation": float("nan")}, {"xy_hole_compensation": float("inf")},
                             {"xy_hole_compensation": -0.51}, {"xy_hole_compensation": 0.51},
                             {"xy_contour_compensation": -.51}, {"xy_contour_compensation": .51},
                             {"xy_contour_compensation": True}, {"xy_contour_compensation": "-0.2"},
                             {"xy_contour_compensation": float("nan")}, {"xy_contour_compensation": float("inf")}):
                code, _ = await self.post("/api/slice", {"confirm": True, "settings": settings})
                self.assertEqual(code, 400)
            self.assertEqual(self.server.work.state["phase"], "model_ready")
            self.assertFalse(self.server.work.state["busy"])
            slicer.assert_not_called(); client.assert_not_called()
            self.assertEqual((await self.post("/api/save", {"confirm": True, "remote_name": "test.gcode", "settings": {}}))[0], 400)

    async def test_web_quality_settings_recorded_and_locked_to_artifact(self):
        self.configure_fake_orca()
        await self.file("model.stl", b"solid synthetic\nendsolid synthetic")
        settings = {"layer_height": 0.12, "brim": "outer", "brim_width": 5,
                    "xy_hole_compensation": 0.2, "xy_contour_compensation": -0.2}
        with patch("finderlab.web.FinderClient") as client:
            code, _ = await self.post("/api/slice", {"confirm": True, "settings": settings})
            self.assertEqual(code, 200)
            state = await self.finish()
            client.assert_not_called()
        self.assertEqual(state["slice_settings"], settings)
        self.assertEqual(state["effective_quality"]["layer_height"], "0.12")
        self.assertEqual(state["effective_quality"]["brim_width"], "5")
        self.assertEqual(state["effective_quality"]["initial_layer_print_height"], "0.2")
        self.assertEqual(state["effective_quality"]["xy_hole_compensation"], "0.2")
        self.assertEqual(state["effective_quality"]["xy_contour_compensation"], "-0.2")
        manifest = json.loads((Path(state["capture"]) / "manifest.json").read_text())
        self.assertEqual(manifest["metadata"]["slice_settings"], settings)
        self.assertEqual((await self.post("/api/slice", {"confirm": True, "settings": {"brim": "off"}}))[0], 409)
        self.assertEqual(self.server.work.state["slice_settings"], settings)
        await self.post("/api/discard", {"confirm": True})
        self.assertIsNone(self.server.work.state["slice_settings"])

    async def test_3mf_file_is_a_model_not_direct_upload_then_offline_slice(self):
        from test_3mf import package
        self.configure_fake_orca()
        self.assertEqual((await self.file("tool.3mf",package()))[0],200)
        self.assertEqual(self.server.work.state["phase"],"model_ready")
        self.assertEqual(self.server.work.state["suggested_name"],"tool.gcode")
        self.assertFalse(self.server.work.state["artifact"])
        with patch("finderlab.web.FinderClient") as client:
            self.assertEqual((await self.post("/api/save",{"confirm":True,"remote_name":"tool.gcode"}))[0],409)
            self.assertEqual((await self.post("/api/slice",{"confirm":True}))[0],200)
            state=await self.finish()
            client.assert_not_called()
        self.assertTrue(state["sliced"])
        self.assertEqual((await self.request("GET","/api/artifact"))[1],PAYLOAD)

    async def test_slice_transform_is_typed_source_bound_and_snapshot_locked(self):
        from test_model_transform import ASCII
        self.configure_fake_orca()
        from test_model_transform import MACHINE
        machine_path=self.server.work.config.slicing.machine
        machine_path.write_text(json.dumps(json.loads(machine_path.read_bytes())|MACHINE))
        await self.file('part.stl',ASCII)
        digest=self.server.work.state['source_sha256'];source_id=self.server.work.state['source_id']
        for transform in ({'scale':True},{'z':1},{'x':71},{'rotate_x':float('inf')}):
            self.assertEqual((await self.post('/api/slice',{'confirm':True,'transform':transform,'source_sha256':digest}))[0],400)
        self.assertEqual((await self.post('/api/slice',{'confirm':True,'transform':{'scale':2},'source_sha256':'old'}))[0],409)
        self.assertEqual((await self.post('/api/slice',{'confirm':True,'transform':{},'source_sha256':digest,'source_id':'old-slot'}))[0],409)
        self.assertIsNone(self.server.work.task)
        # Fake native CLI still checks the actual arranged-disabled/baked input.
        fake=self.server.work.config.slicing.orca
        path=Path(fake);path.write_text(path.read_text().replace('value("--arrange") == "1"','value("--arrange") == "0"').replace('name == "model.stl"','name == "placed.stl"'))
        with patch('finderlab.web.FinderClient') as printer:
            self.assertEqual((await self.post('/api/slice',{'confirm':True,'transform':{'scale':2,'x':30},'source_sha256':digest,'source_id':source_id}))[0],200)
            state=await self.finish()
            self.assertEqual(state['phase'],'review',state.get('error'));self.assertEqual(state['model_transform']['scale'],2.)
            self.assertEqual(state['source_sha256'],digest);self.assertEqual(state['source_id'],source_id)
            self.assertEqual((await self.request('GET','/api/model'))[1],ASCII)
            self.assertEqual((await self.post('/api/slice',{'confirm':True,'transform':{},'source_sha256':digest}))[0],409)
            printer.assert_not_called()
        await self.post('/api/discard',{'confirm':True});await self.file('part.stl',ASCII)
        self.assertNotEqual(self.server.work.state['source_id'],source_id)
        self.assertEqual(self.server.work.state['source_sha256'],digest)
        self.assertIsNone(self.server.work.state['model_transform'])
        self.assertEqual((await self.post('/api/slice',{'confirm':True,'transform':{},'source_sha256':digest,'source_id':source_id}))[0],409)

    async def test_stl_model_preview_before_and_after_slice_keeps_original_source(self):
        self.configure_fake_orca()
        raw=(b"solid synthetic\nfacet normal 0 0 1\nouter loop\n"
             b"vertex 0 0 0\nvertex 1 0 0\nvertex 0 1 0\nendloop\nendfacet\nendsolid synthetic\n")
        with patch("finderlab.web.FinderClient") as client:
            self.assertEqual((await self.request("GET","/api/model"))[0],404)
            await self.file("part.stl",raw)
            source_hash=hashlib.sha256(raw).hexdigest();tag='"'+source_hash+'"'
            self.assertTrue(self.server.work.state["model"])
            self.assertEqual((await self.request("GET","/api/model",headers={"X-Finder-Token":""}))[0],403)
            code,body=await self.request("GET","/api/model",headers={"If-Match":tag})
            self.assertEqual(code,200);self.assertEqual(body,raw)
            self.assertEqual((await self.request("GET","/api/model",headers={"If-Match":'"old"'}))[0],412)
            await self.post("/api/slice",{"confirm":True});state=await self.finish()
            self.assertNotEqual(state["sha256"],source_hash)
            self.assertEqual(state["source_sha256"],source_hash)
            self.assertEqual((await self.request("GET","/api/model",headers={"If-Match":tag}))[1],raw)
            self.assertEqual((await self.request("GET","/api/artifact"))[1],PAYLOAD)
            client.assert_not_called()

    async def test_3mf_model_preview_is_bounded_cached_geometry_without_native_or_printer(self):
        from test_3mf import package
        with patch("finderlab.web.FinderClient") as client,patch("finderlab.web.slice_model") as slicer:
            await self.file("part.3mf",package(extra={"Metadata/preset":"start_gcode=M112"}))
            tag='"'+self.server.work.state["source_sha256"]+'"'
            code,body=await self.request("GET","/api/model",headers={"If-Match":tag})
            self.assertEqual(code,200);self.assertEqual(len(body),134);self.assertNotIn(b"M112",body)
            cached=self.server.work.model_cache[0]
            self.assertTrue(cached.is_file())
            with patch("asyncio.create_subprocess_exec",side_effect=AssertionError("cache should be reused")):
                self.assertEqual((await self.request("GET","/api/model",headers={"If-Match":tag}))[1],body)
            self.assertEqual(self.server.work.state["phase"],"model_ready")
            self.assertFalse(self.server.work.state["busy"])
            await self.post("/api/discard",{"confirm":True})
            self.assertFalse(cached.exists())
            self.assertEqual((await self.request("GET","/api/model"))[0],404)
            client.assert_not_called();slicer.assert_not_called()
        self.assertEqual(list(self.server.work.folder.glob("captures/*")),[])

    async def test_unsupported_3mf_model_preview_does_not_break_source_slot(self):
        await self.file("bad.3mf",b"invalid archive")
        self.assertEqual((await self.request("GET","/api/model"))[0],422)
        self.assertFalse(self.server.work.state["busy"])
        self.assertEqual(self.server.work.state["phase"],"model_ready")
        self.assertIsNone(self.server.work.model_cache)
        self.assertFalse((self.server.work.slot/"model-preview.stl").exists())

    async def test_model_preview_cleanup_io_error_still_restores_slot_state(self):
        from test_3mf import package
        from unittest.mock import AsyncMock
        from types import SimpleNamespace
        await self.file("part.3mf",package())
        process=SimpleNamespace(returncode=1,communicate=AsyncMock(return_value=(b"{}",None)))
        with patch("asyncio.create_subprocess_exec",new=AsyncMock(return_value=process)),patch.object(Path,"unlink",side_effect=OSError("read-only filesystem")):
            with self.assertRaises(OSError): await self.server.work.model_geometry()
        self.assertFalse(self.server.work.state["busy"])
        self.assertEqual(self.server.work.state["phase"],"model_ready")
        self.assertTrue(self.server.work.source.exists())

    async def test_model_preview_cancel_reaps_converter_and_unlocks_slot(self):
        from test_3mf import package
        from finderlab.web import WebError
        from unittest.mock import AsyncMock
        from types import SimpleNamespace
        await self.file("part.3mf",package())
        entered=asyncio.Event()
        async def communicate():
            entered.set();await asyncio.Event().wait()
        process=SimpleNamespace(pid=123456,returncode=None,communicate=communicate,wait=AsyncMock())
        with patch("asyncio.create_subprocess_exec",new=AsyncMock(return_value=process)),patch("finderlab.web.os.killpg") as kill:
            task=asyncio.create_task(self.server.work.model_geometry())
            await asyncio.wait_for(entered.wait(),2)
            self.assertTrue(self.server.work.state["busy"])
            with self.assertRaises(WebError): self.server.work.discard()
            task.cancel();await asyncio.gather(task,return_exceptions=True)
            kill.assert_called_once_with(123456,signal.SIGKILL)
            process.wait.assert_awaited_once()
        self.assertFalse(self.server.work.state["busy"])
        self.assertEqual(self.server.work.state["phase"],"model_ready")

    async def test_preview_artifact_identity_and_static_routes_are_read_only(self):
        from finderlab.web import STATIC_FILES
        with patch("finderlab.web.FinderClient") as client:
            self.assertEqual((await self.request("GET", "/api/artifact"))[0],404)
            for route in STATIC_FILES:
                self.assertEqual((await self.request("GET",route))[0],200,route)
            self.assertEqual((await self.request("GET","/vendor/three/../../web.py"))[0],404)
            payload=b"G21\nG90\nM82\nG92 E0\nG1 X0 Y0 Z.2\nG1 X1 E1\n"
            await self.file("preview.gcode",payload)
            tag='"'+hashlib.sha256(payload).hexdigest()+'"'
            code,body=await self.request("GET","/api/artifact",headers={"If-Match":tag})
            self.assertEqual(code,200);self.assertEqual(body,payload)
            self.assertIn(('ETag: '+tag).encode(),self.last_headers)
            self.assertIn(b"worker-src 'self'",self.last_headers)
            self.assertEqual((await self.request("GET","/api/artifact",headers={"If-Match":'"stale"'}))[0],412)
            self.server.work.state["busy"]=True
            self.assertEqual((await self.request("GET","/api/artifact",headers={"If-Match":tag}))[0],409)
            self.server.work.state["busy"]=False
            await self.post("/api/discard",{"confirm":True})
            self.assertEqual((await self.request("GET","/api/artifact",headers={"If-Match":tag}))[0],404)
            client.assert_not_called()
        self.assertEqual(list(self.server.work.folder.glob("captures/*")),[])

    async def prepare_gx_slice(self):
        from test_gx_generation import CODE,PROCESS,FILAMENT
        from test_model_transform import ASCII
        self.configure_fake_orca()
        cfg=self.server.work.config.slicing
        fake=Path(cfg.orca);fake.write_text(fake.read_text().replace(f'PAYLOAD={PAYLOAD!r}',f'PAYLOAD={CODE!r}'))
        for path,values in ((cfg.process,PROCESS),(cfg.filament,FILAMENT)):
            path.write_text(json.dumps(json.loads(path.read_bytes())|values))
        await self.file('part.stl',ASCII)
        await self.post('/api/slice',{'confirm':True});state=await self.finish()
        self.assertEqual(state['phase'],'review',state['error']);self.assertTrue(state['gx_metadata'])
        return {'confirm':True,'artifact_sha256':state['sha256'],'source_id':state['source_id']}

    async def test_gx_export_is_offline_source_bound_exact_and_selects_real_format(self):
        from test_gx_generation import CODE
        from tools.extract_gx_preview import decode_preview
        with patch('finderlab.web.FinderClient') as client:
            self.assertEqual((await self.post('/api/gx',{'confirm':True}))[0],409)
            data=await self.prepare_gx_slice()
            self.assertEqual((await self.post('/api/gx',data|{'artifact_sha256':'old'}))[0],409)
            self.assertEqual((await self.post('/api/gx',data|{'host':'192.0.2.1'}))[0],400)
            old=self.server.work.artifact
            self.assertEqual((await self.post('/api/gx',data))[0],200)
            state=await self.finish()
            self.assertEqual(state['phase'],'review',state['error']);self.assertTrue(state['gx_generated']);self.assertTrue(state['sliced'])
            self.assertEqual(state['suggested_name'],'part.gx');self.assertEqual(old.read_bytes(),CODE)
            code,body=await self.request('GET','/api/artifact');self.assertEqual(code,200);self.assertEqual(body[14512:],CODE)
            self.assertEqual(decode_preview(body)[0]['width'],80)
            self.assertEqual((await self.request('GET','/api/gx-thumbnail?v=old'))[0],412)
            self.assertEqual((await self.request('GET','/api/gx-thumbnail?v='+state['sha256']))[1],decode_preview(body)[1])
            self.assertEqual((await self.post('/api/gx',data))[0],409)
            self.assertEqual((await self.post('/api/save',{'confirm':True,'remote_name':'part.gx'}))[0],409,'wrapping cannot bypass generated-output gate')
            client.assert_not_called()
        self.server.work.config=replace(self.server.work.config,allow_sliced_upload=True)
        self.assertEqual((await self.post('/api/save',{'confirm':True,'remote_name':'wrong.gcode'}))[0],400)
        await self.post('/api/save',{'confirm':True,'remote_name':'part.gx','start_after_upload':False})
        state=await self.finish();self.assertTrue(state['saved']);self.assertEqual(self.mock.files['part.gx'],body);self.assertIsNone(self.mock.active_file)

    async def test_gx_failure_preserves_original_artifact_and_never_starts(self):
        from test_gx_generation import CODE
        data=await self.prepare_gx_slice();self.server.work.source.write_bytes(b'changed source')
        with patch('finderlab.web.FinderClient') as client:
            await self.post('/api/gx',data);state=await self.finish()
            self.assertEqual(state['phase'],'failed');self.assertFalse(state['gx_generated'])
            self.assertEqual(self.server.work.artifact.read_bytes(),CODE)
            self.assertFalse(self.server.work.artifact.with_suffix('.gx').exists());client.assert_not_called()

    async def test_gx_unavailable_metadata_does_not_break_slice(self):
        self.configure_fake_orca()
        await self.file('part.stl',b'solid fake\nendsolid fake')
        await self.post('/api/slice',{'confirm':True});state=await self.finish()
        self.assertEqual(state['phase'],'review');self.assertIsNone(state['gx_metadata'])
        self.assertEqual((await self.post('/api/gx',{'confirm':True,'source_id':state['source_id'],'artifact_sha256':state['sha256']}))[0],409)

    async def test_priming_guard_failure_exposes_no_artifact_or_combined_save(self):
        import re
        from test_model_transform import ASCII,MACHINE
        from test_priming_review import SKIRT
        self.configure_fake_orca()
        config=self.server.work.config.slicing
        machine=json.loads(config.machine.read_bytes())|MACHINE;config.machine.write_text(json.dumps(machine))
        bad=re.sub(r'X([+-]?\d+)',lambda m:'X'+str(int(m[1])+68),SKIRT).encode()
        fake=Path(config.orca);fake.write_text(fake.read_text().replace(f'PAYLOAD={PAYLOAD!r}',f'PAYLOAD={bad!r}'))
        self.server.work.config=replace(self.server.work.config,slicing=replace(config,check_priming=True),enable_job_controls=True,allow_sliced_upload=True)
        await self.file('source.stl',ASCII)
        with patch('finderlab.web.FinderClient') as client:
            await self.post('/api/slice',{'confirm':True});state=await self.finish()
            self.assertEqual(state['phase'],'failed');self.assertIn('margin',state['error'])
            self.assertFalse(state['artifact']);self.assertEqual((await self.request('GET','/api/artifact'))[0],404)
            self.assertEqual((await self.post('/api/save',{'confirm':True,'remote_name':'never.gcode','start_after_upload':True,
                             'artifact_sha256':state['sha256'],'source_id':state['source_id']}))[0],409)
            client.assert_not_called()

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
