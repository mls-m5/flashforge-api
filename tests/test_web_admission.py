"""Workbench admission HTTP contracts; owned ephemeral loopback/fake Orca, no hardware."""

from dataclasses import replace
from unittest.mock import patch
from finderlab.web import WebServer
from web_helpers import WebTestCase


class WebAdmissionTests(WebTestCase):
    async def test_web_capacity_archives_complete_history_not_current_slot(self):
        from finderlab.capture import Capture
        work=self.server.work
        old=Capture(work.folder/'captures','client',metadata={'operation':'monitor'})
        old.event('synthetic_test',message='x'*2048);old.close()
        raw=(old.path/'events.jsonl').read_bytes();old_path=old.path
        await self.file('current.stl',b'solid original\nendsolid original')
        source=work.source;before=source.read_bytes()
        total=sum(p.stat().st_size for p in work.folder.rglob('*') if p.is_file())
        size=sum(p.stat().st_size for p in old_path.rglob('*') if p.is_file())
        with patch('finderlab.web.STORAGE_LIMIT',total-size+1024):work.capacity(100)
        self.assertFalse(old_path.exists());self.assertEqual((work.folder/'archive/captures'/old_path.name/'events.jsonl').read_bytes(),raw)
        self.assertEqual(source.read_bytes(),before);self.assertIn('Automatically archived',work.state['storage_notice'])
        self.assertIsNone(work.task)
        for value in (0,127,2049,True,512.5):
            with self.assertRaises(ValueError):replace(self.config,storage_limit_mib=value)
        self.assertEqual(replace(self.config,storage_limit_mib=512).storage_limit,512*1024**2)

    async def test_slice_http_admission_automatically_archives_old_logs_without_retry(self):
        from finderlab.capture import Capture
        self.configure_fake_orca()
        await self.file('part.stl',b'solid synthetic\nendsolid synthetic')
        old=Capture(self.server.work.folder/'captures','client',metadata={'operation':'monitor'})
        old.event('test',payload='x'*4096);old.close()
        before=(old.path/'manifest.json').read_bytes()
        used=sum(p.stat().st_size for p in self.server.work.folder.rglob('*') if p.is_file())
        size=sum(p.stat().st_size for p in old.path.rglob('*') if p.is_file())
        with patch('finderlab.web.STORAGE_LIMIT',used-size+73*1024**2+1024),patch('finderlab.web.FinderClient') as client:
            code,_=await self.post('/api/slice',{'confirm':True})
            self.assertEqual(code,200);state=await self.finish()
            self.assertEqual(state['phase'],'review',state['error']);client.assert_not_called()
        self.assertFalse(old.path.exists())
        self.assertEqual((self.server.work.folder/'archive/captures'/old.path.name/'manifest.json').read_bytes(),before)
        self.assertIn('Automatically archived',state['storage_notice'])

    async def test_model_preview_get_cannot_trigger_automatic_archive(self):
        from finderlab.capture import Capture
        from finderlab.model_3mf import MAX_TRIANGLES
        from test_3mf import package
        await self.file('part.3mf',package())
        old=Capture(self.server.work.folder/'captures','client',metadata={'operation':'monitor'})
        old.event('test',payload='x'*4096);old.close()
        used=sum(p.stat().st_size for p in self.server.work.folder.rglob('*') if p.is_file())
        size=sum(p.stat().st_size for p in old.path.rglob('*') if p.is_file())
        reserve=84+MAX_TRIANGLES*50+4096
        with patch('finderlab.web.STORAGE_LIMIT',used-size+reserve+512):
            code,_=await self.request('GET','/api/model')
        self.assertEqual(code,507);self.assertTrue(old.path.exists())
        self.assertFalse((self.server.work.folder/'archive').exists())

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

    async def test_storage_quota_and_workspace_lock(self):
        with patch("finderlab.web.STORAGE_LIMIT", 100):
            self.assertEqual((await self.file("quota.gx"))[0], 507)
        other = WebServer(self.config)
        with self.assertRaises(OSError):
            await other.__aenter__()
        self.assertFalse(self.server.work.state["busy"])
