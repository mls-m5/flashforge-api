"""Read-only status from synthetic proxy captures. No TCP connection needed."""

from datetime import datetime, timedelta, timezone
import hashlib
from pathlib import Path
import unittest
from unittest.mock import patch

from finderlab.capture import Capture
from finderlab.passive_status import status_from_capture
from helpers import workspace_tempdir

STAMP = datetime(2030, 1, 1, tzinfo=timezone.utc)
TEMP = b"CMD M105 Received.\r\nT0:220 /220 B:0 /0\r\nok\r\n"
STATUS = b"CMD M119 Received.\r\nEndstop: X-max: 0 Y-max: 0 Z-max: 0\r\nMachineStatus: BUILDING_FROM_SD\r\nMoveMode: MOVING\r\nok\r\n"
PROGRESS = b"CMD M27 Received.\r\nSD printing byte 76580/76579\r\nok\r\n"


class PassiveStatusTests(unittest.TestCase):
    def setUp(self):
        self.temp = workspace_tempdir(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def record(self, label="a", chunks=None, port=9000):
        root = self.root / "captures"
        with patch("finderlab.capture.utc_now", return_value=STAMP.isoformat()):
            capture = Capture(root, "proxy", metadata={"config": {"host": "127.0.0.1", "port": port,
                              "target_host": "192.0.2.10", "target_port": 8899}})
            session = capture.session()
            for chunk in chunks if chunks is not None else [TEMP + STATUS + PROGRESS]:
                session.data("server_to_client", chunk)
            capture.close()
        folder = root / label
        capture.path.rename(folder)
        return folder

    def status(self, source, age=2):
        return status_from_capture(source, "127.0.0.1", 9000, now=STAMP + timedelta(seconds=age))

    def test_complete_fragmented_coalesced_status_and_over_total_progress(self):
        raw = b"CMD M17 Received.\r\nok\n" + TEMP + STATUS + PROGRESS
        folder = self.record(chunks=[raw[:23], raw[23:48], raw[48:-1], raw[-1:]])
        before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.rglob("*") if p.is_file()}
        data = self.status(folder)
        self.assertFalse(data["stale"])
        self.assertEqual(data["samples"]["M105"]["values"]["nozzle"], 220)
        self.assertEqual(data["samples"]["M119"]["values"]["move"], "MOVING")
        progress = data["samples"]["M27"]["values"]
        self.assertEqual(progress["percent"], 100)
        self.assertTrue(progress["over_total"])
        self.assertFalse(progress["completion_inferred"])
        self.assertEqual(before, {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in before})

    def test_stale_clock_skew_and_missing_metric_are_honest(self):
        folder = self.record()
        data = self.status(folder, age=30)
        self.assertTrue(data["stale"])
        self.assertTrue(all(s["stale"] for s in data["samples"].values()))
        self.assertTrue(self.status(folder, age=-60)["stale"])
        other = self.record(label="b", chunks=[TEMP])
        self.assertTrue(self.status(other)["stale"])
        self.assertNotIn("M119", self.status(other)["samples"])

    def test_latest_matching_proxy_no_wrong_endpoint_or_cross_session_merging(self):
        self.record(label="a")
        newest = self.record(label="z", port=9999)
        data = self.status(self.root / "captures")
        self.assertEqual(data["source"], "a")
        self.assertFalse(self.status(newest)["samples"])
        # A different newest matching capture has only progress; no old temp/status is inherited.
        self.record(label="y", chunks=[PROGRESS])
        data = self.status(self.root / "captures")
        self.assertEqual(set(data["samples"]), {"M27"})
        self.assertTrue(data["stale"])

    def test_new_session_does_not_inherit_other_session_temperature(self):
        with patch("finderlab.capture.utc_now", return_value=STAMP.isoformat()):
            capture = Capture(self.root / "multi", "proxy", metadata={"config": {"host": "127.0.0.1", "port": 9000}})
            capture.session().data("server_to_client", TEMP + STATUS + PROGRESS)
            capture.session().data("server_to_client", STATUS)
            capture.close()
        data = self.status(capture.path)
        self.assertEqual(data["session"], "s0002")
        self.assertEqual(set(data["samples"]), {"M119"})
        self.assertTrue(data["stale"])

    def test_partial_and_malformed_replies_not_presented_as_fresh(self):
        folder = self.record(chunks=[TEMP[:-1]])
        self.assertFalse(self.status(folder)["samples"])
        folder = self.record(label="b", chunks=[TEMP + b"CMD M105 Received.\r\nError: synthetic\r\nok\r\n"])
        data = self.status(folder)
        self.assertIsNone(data["samples"]["M105"]["values"])
        self.assertTrue(data["samples"]["M105"]["stale"])
        error_body = TEMP.replace(b"T0:", b"Error: synthetic\r\nT0:")
        folder = self.record(label="d", chunks=[error_body])
        self.assertIsNone(self.status(folder)["samples"]["M105"]["values"])
        folder = self.record(label="c", chunks=[b"CMD M27 Received.\r\nSD printing byte 0/0\r\nok\r\n"])
        self.assertIsNone(self.status(folder)["samples"]["M27"]["values"]["percent"])

    def test_disabled_missing_corrupt_and_symlink_sources(self):
        self.assertFalse(self.status(None)["enabled"])
        self.assertTrue(self.status(self.root / "missing")["stale"])
        folder = self.record()
        alias = self.root / "alias"; alias.symlink_to(folder, target_is_directory=True)
        self.assertFalse(self.status(alias)["samples"])
        (folder / "manifest.json").write_text('{"incomplete":')
        self.assertFalse(self.status(folder)["samples"])

    def test_running_capture_and_partial_event_tail(self):
        folder = self.record()
        manifest = folder / "manifest.json"
        import json
        d = json.loads(manifest.read_text()); d["complete"] = False
        manifest.write_text(json.dumps(d))
        with (folder / "events.jsonl").open("ab") as file: file.write(b'{"partial":')
        data = self.status(folder)
        self.assertFalse(data["capture_finalized"])
        self.assertFalse(data["stale"])
