"""Workbench manual HTTP contracts; owned ephemeral loopback/fake Orca, no hardware."""

import asyncio
from contextlib import asynccontextmanager
from dataclasses import replace
import json
from unittest.mock import patch
from finderlab.web import serve_workbench
from web_helpers import WebTestCase


class WebManualTests(WebTestCase):
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
