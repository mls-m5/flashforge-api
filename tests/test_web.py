"""Workbench core HTTP contracts; owned ephemeral loopback/fake Orca, no hardware."""

import asyncio
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from finderlab.client import ClientConfig
from finderlab.web import MODEL_LIMIT, PRINT_LIMIT, WebConfig, serve_workbench, suggested_name
from web_helpers import WebTestCase


class WebTests(WebTestCase):
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
