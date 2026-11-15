"""Pinned reviewed MIT browser dependency; no runtime fetching."""
import hashlib
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]/'finderlab/webstatic/vendor/three'
class PreviewVendorTests(unittest.TestCase):
    def test_pinned_blobs_and_single_documented_local_import_change(self):
        blobs={'LICENSE':'4c40a1ef62450b857c3b2aaf294936304cd552d965fbcd9d32d4c5bcf4ba4454',
               'three.module.min.js':'08fd7545d13d2c7fb65ab691530a802dafefd638596501854f267d0fb13c39e7'}
        for name,sha in blobs.items(): self.assertEqual(hashlib.sha256((ROOT/name).read_bytes()).hexdigest(),sha)
        controls=(ROOT/'OrbitControls.js').read_bytes()
        self.assertEqual(controls.count(b"from './three.module.min.js'"),1)
        original=controls.replace(b"from './three.module.min.js'",b"from 'three'")
        self.assertEqual(hashlib.sha256(original).hexdigest(),'80efaadea4f8a636a65fb0bd08bfef62f3d93a0bb94e2e7500f23176c5c07f4e')
        self.assertIn(b'Permission is hereby granted',(ROOT/'LICENSE').read_bytes())
