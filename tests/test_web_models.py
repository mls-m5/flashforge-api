"""Workbench models HTTP contracts; owned ephemeral loopback/fake Orca, no hardware."""

import asyncio
import hashlib
import json
import signal
from pathlib import Path
from unittest.mock import patch
from test_slicer import PAYLOAD
from web_helpers import WebTestCase


class WebModelsTests(WebTestCase):
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
        with patch("asyncio.create_subprocess_exec",new=AsyncMock(return_value=process)),patch("finderlab.web_files.os.killpg") as kill:
            task=asyncio.create_task(self.server.work.model_geometry())
            await asyncio.wait_for(entered.wait(),2)
            self.assertTrue(self.server.work.state["busy"])
            with self.assertRaises(WebError): self.server.work.discard()
            task.cancel();await asyncio.gather(task,return_exceptions=True)
            kill.assert_called_once_with(123456,signal.SIGKILL)
            process.wait.assert_awaited_once()
        self.assertFalse(self.server.work.state["busy"])
        self.assertEqual(self.server.work.state["phase"],"model_ready")
