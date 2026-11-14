"""Reviewed text derivatives are deterministic and reject unreviewed inputs."""

import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from tools.export_reviewed_traces import REVIEWED, render

ROOT = Path(__file__).resolve().parents[1]


class ReviewedTraceTests(unittest.TestCase):
    def test_committed_derivatives_are_reproducible(self):
        outputs = render()
        folder = ROOT / "docs/traces"
        for name, expected in outputs.items():
            with self.subTest(name=name):
                self.assertEqual((folder / name).read_bytes(), expected.encode())
        manifest = json.loads(outputs["manifest.json"])
        self.assertTrue(manifest["not_replayable"])
        self.assertEqual(manifest["source_fixture_sha256"], REVIEWED)
        self.assertEqual(manifest["outputs"]["idle-prefix.log"], hashlib.sha256(outputs["idle-prefix.log"].encode()).hexdigest())
        self.assertIn("ORIGINAL PAYLOAD OMITTED", outputs["upload-facts.log"])
        self.assertIn("SYNTHETIC standard CRC32 vector", outputs["upload-facts.log"])

    def test_fixture_change_requires_manual_review(self):
        root = ROOT / ".tmp"
        root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="trace-review-", dir=root) as folder:
            fixture_dir = Path(folder)
            for name in REVIEWED:
                (fixture_dir / name).write_bytes((ROOT / "tests/fixtures" / name).read_bytes())
            (fixture_dir / next(iter(REVIEWED))).write_bytes(b"changed after privacy review")
            with self.assertRaisesRegex(ValueError, "changed since privacy review"):
                render(fixture_dir)


if __name__ == "__main__":
    unittest.main()
