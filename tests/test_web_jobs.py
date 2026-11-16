"""Workbench jobs HTTP contracts; owned ephemeral loopback/fake Orca, no hardware."""

from dataclasses import replace
import hashlib
import json
from pathlib import Path
from unittest.mock import patch
from finderlab.client import FinderClient
from finderlab.web import WebCapture
from web_helpers import WebTestCase


class WebJobsTests(WebTestCase):
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
