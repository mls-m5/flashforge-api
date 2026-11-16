"""Workbench gx HTTP contracts; owned ephemeral loopback/fake Orca, no hardware."""

from dataclasses import replace
import json
from pathlib import Path
from unittest.mock import patch
from test_slicer import PAYLOAD
from web_helpers import WebTestCase


class WebGxTests(WebTestCase):
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
