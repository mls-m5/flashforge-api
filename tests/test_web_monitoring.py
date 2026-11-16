"""Workbench monitoring HTTP contracts; owned ephemeral loopback/fake Orca, no hardware."""

from dataclasses import replace
import json
from unittest.mock import patch
from finderlab.web import WebCapture, WebServer
from web_helpers import WebTestCase


class WebMonitoringTests(WebTestCase):
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
