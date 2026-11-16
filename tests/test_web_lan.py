"""Workbench lan HTTP contracts; owned ephemeral loopback/fake Orca, no hardware."""

from dataclasses import replace
import json
from unittest.mock import patch
from finderlab.web import WebServer
from test_slicer import PAYLOAD
from web_helpers import WebTestCase


class WebLanTests(WebTestCase):
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
