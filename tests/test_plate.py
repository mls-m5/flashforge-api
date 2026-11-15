import hashlib
import json
from pathlib import Path
import unittest
from finderlab.plate import normalize_plate,assemble
from finderlab.model_transform import read_stl
from helpers import workspace_tempdir
from test_model_transform import ASCII,MACHINE

class PlateTests(unittest.TestCase):
    def setUp(self):
        self.temp=workspace_tempdir();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.source=self.root/'source.stl';self.source.write_bytes(ASCII)
        self.entries=[dict(id=str(i),path=str(self.source),sha256=hashlib.sha256(ASCII).hexdigest(),transform={'x':x}) for i,x in enumerate((-20,20))]

    def test_two_originals_bake_disjoint_positions_without_source_mutation(self):
        output=self.root/'plate.stl';info=assemble(self.entries,MACHINE,output)
        vertices=read_stl(output);self.assertEqual(len(vertices),6)
        self.assertAlmostEqual(min(v[0] for v in vertices[:3]),-22)
        self.assertAlmostEqual(min(v[0] for v in vertices[3:]),18)
        self.assertEqual(self.source.read_bytes(),ASCII);self.assertEqual(info['sha256'],hashlib.sha256(output.read_bytes()).hexdigest())
        self.assertFalse(info['sequential_printing']);self.assertEqual(info['triangles'],2)

    def test_stale_duplicate_missing_injected_or_invalid_layout_rejected(self):
        good=[dict(id=e['id'],transform=e['transform']) for e in self.entries]
        self.assertEqual(len(normalize_plate(good,['0','1'])),2)
        for value in (None,[],good[:1],good+[good[0]],[good[0],good[0]], [good[0],dict(id='x',transform={})],
                      [good[0],dict(id='1',transform=None)],[good[0],dict(id='1',transform={'scale':True})],
                      [good[0],dict(id='1',transform={},path='/evil')]):
            with self.assertRaises(ValueError):normalize_plate(value,['0','1'])

    def test_overlap_bounds_and_identity_errors_do_not_publish(self):
        for entries in ([dict(e,transform={}) for e in self.entries],
                        [self.entries[0],dict(self.entries[1],transform={'x':70})],
                        [self.entries[0],dict(self.entries[1],sha256='old')]):
            output=self.root/'bad.stl'
            with self.assertRaises(ValueError):assemble(entries,MACHINE,output)
            self.assertFalse(output.exists())
