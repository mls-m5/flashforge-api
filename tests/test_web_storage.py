import json
from pathlib import Path
import unittest
from unittest.mock import patch
from finderlab.web_storage import admit,measure,StorageError
from helpers import workspace_tempdir

class WebStorageTests(unittest.TestCase):
    def setUp(self):
        self.temp=workspace_tempdir();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)

    def capture(self,name='old',complete=True,closed=True,ended='2000-01-01T00:00:00+00:00'):
        folder=self.root/'captures'/name;folder.mkdir(parents=True)
        data=b'private synthetic evidence\0~M29'*100
        (folder/'raw.bin').write_bytes(data)
        (folder/'manifest.json').write_text(json.dumps(dict(capture_id=name,complete=complete,ended_utc=ended,
                                                           sessions=[dict(session_id='synthetic',closed=closed)])))
        return folder

    def test_archives_intact_inside_persistent_volume_and_excludes_from_active_budget(self):
        old=self.capture();before={p.name:p.read_bytes() for p in old.iterdir()};size,count=measure(self.root)
        total,count,moved=admit(self.root,100,200)
        self.assertEqual(len(moved),1);self.assertLessEqual(total+100,200);self.assertFalse(old.exists())
        target=self.root/'archive/captures/old'
        self.assertEqual(before,{p.name:p.read_bytes() for p in target.iterdir()})
        self.assertEqual(measure(self.root,exclude_archive=True)[0],total)
        self.assertGreater(measure(self.root)[0],total)
        record=json.loads((self.root/'archive/index.jsonl').read_text());self.assertEqual(record['capture_id'],'old')

    def test_never_moves_active_incomplete_open_or_current_referenced_capture(self):
        active=self.capture('active',complete=False);open_record=self.capture('open',closed=False)
        current=self.capture('current');no_end=self.capture('no-end',ended=None)
        total,_,moved=admit(self.root,100,200,protected=[current])
        self.assertGreater(total+100,200);self.assertEqual(moved,[])
        for p in (active,open_record,current,no_end):self.assertTrue(p.exists())
        self.assertFalse((self.root/'archive').exists())

    def test_oldest_first_no_automatic_deletion_and_no_move_when_unneeded_or_disabled(self):
        oldest=self.capture('oldest');newer=self.capture('newer',ended='2001-01-01T00:00:00+00:00')
        total,_=measure(self.root)
        self.assertEqual(admit(self.root,10,total+20)[2],[])
        self.assertEqual(admit(self.root,10,100,auto_archive=False)[2],[])
        size,_=measure(oldest)
        _,_,moved=admit(self.root,10,total-size+20)
        self.assertEqual([r['capture_id'] for r in moved],['oldest']);self.assertTrue(newer.exists())
        self.assertTrue((self.root/'archive/captures/oldest').exists())

    def test_archive_bounds_symlinks_and_collision_do_not_destroy_evidence(self):
        original=self.capture()
        with patch('finderlab.web_storage.ARCHIVE_BYTES',1),self.assertRaisesRegex(StorageError,'archive budget'):
            admit(self.root,100,200)
        self.assertTrue(original.exists())
        target=self.root/'archive/captures/old';target.mkdir(parents=True);(target/'keep').write_text('untouched')
        self.assertEqual(admit(self.root,100,200)[2],[]);self.assertTrue(original.exists());self.assertEqual((target/'keep').read_text(),'untouched')
        (self.root/'bad-link').symlink_to(original,target_is_directory=True)
        with self.assertRaisesRegex(StorageError,'symlink'):admit(self.root,1,200)

    def test_unknown_malformed_or_naive_manifest_not_moved(self):
        folder=self.capture();(folder/'manifest.json').write_text('{bad JSON')
        self.assertEqual(admit(self.root,100,200)[2],[])
        (folder/'manifest.json').write_text(json.dumps(dict(capture_id='old',complete=True,ended_utc='2000-01-01T00:00:00',sessions=[])))
        self.assertEqual(admit(self.root,100,200)[2],[])
