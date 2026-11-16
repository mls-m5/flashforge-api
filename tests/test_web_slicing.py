"""Workbench slicing HTTP contracts; owned ephemeral loopback/fake Orca, no hardware."""

import asyncio
from dataclasses import replace
import json
from pathlib import Path
from unittest.mock import patch
from finderlab.web import WebCapture, Workbench
from test_slicer import PAYLOAD
from web_helpers import WebTestCase


class WebSlicingTests(WebTestCase):
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
