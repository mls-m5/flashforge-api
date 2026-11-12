"""Private recordings are created only in temporary directories."""

import asyncio
import hashlib
import json
import unittest
from unittest.mock import Mock

from finderlab.capture import Capture, CaptureError
from finderlab.simulator import MockConfig, MockPrinter
from helpers import events, stream, workspace_tempdir


class CaptureTests(unittest.TestCase):
    def setUp(self):
        self.temp = workspace_tempdir()
        self.addCleanup(self.temp.cleanup)
        self.capture = Capture(self.temp.name, "test")
        self.addCleanup(self.capture.close)

    def test_history_hashes_offsets_and_safe_previews(self):
        a = self.capture.session(peer=["127.0.0.1", 1])
        chunks = [b"~M115\r", b"\n\x00\xff\x1b[2J" * 100]
        for chunk in chunks:
            seq = a.data("client_to_server", chunk)
            a.event("forward_complete", direction="client_to_server", data_seq=seq)
        a.data("server_to_client", b"ok\r\n")
        a.close("eof")
        b = self.capture.session(peer=["127.0.0.1", 2])
        b.close("timeout")
        before = json.loads((self.capture.path / "manifest.json").read_text())
        self.assertFalse(before["complete"])
        self.capture.close()
        manifest = json.loads((self.capture.path / "manifest.json").read_text())
        self.assertTrue(manifest["complete"])
        self.assertEqual(len(manifest["sessions"]), 2)
        raw = stream(self.capture, a.id, "client_to_server")
        self.assertEqual(raw, b"".join(chunks))
        summary = manifest["sessions"][0]["streams"]["client_to_server"]
        self.assertEqual(summary["length"], len(raw))
        self.assertEqual(summary["sha256"], hashlib.sha256(raw).hexdigest())
        data = [e for e in events(self.capture) if e["type"] == "data"]
        self.assertEqual([e["stream_offset"] for e in data], [0, len(chunks[0]), 0])
        self.assertTrue(data[1]["preview_truncated"])
        self.assertNotIn("\x1b", (self.capture.path / "traffic.log").read_text())
        self.assertEqual(events(self.capture)[-1]["type"], "capture_end")
        seqs = [e["seq"] for e in events(self.capture)]
        self.assertEqual(seqs, sorted(set(seqs)))

    def test_new_runs_do_not_overwrite_history(self):
        other = Capture(self.temp.name, "test")
        other.close()
        self.assertNotEqual(self.capture.path, other.path)
        self.assertTrue((self.capture.path / "manifest.json").exists())

    def test_quota_marks_incomplete_and_stops_recording(self):
        session = self.capture.session()
        self.capture.max_bytes = self.capture.written + 2
        with self.assertRaises(CaptureError):
            session.data("client_to_server", b"too large")
        self.assertTrue(self.capture.failed)
        with self.assertRaises(CaptureError):
            session.data("server_to_client", b"ok")
        self.capture.close()
        manifest = json.loads((self.capture.path / "manifest.json").read_text())
        self.assertFalse(manifest["complete"])
        self.assertEqual(stream(self.capture, session.id, "client_to_server"), b"")

    def test_quota_during_shutdown_still_closes_all_streams(self):
        a, b = self.capture.session(), self.capture.session()
        self.capture.max_bytes = self.capture.written
        self.capture.close()
        self.assertTrue(self.capture.failed)
        self.assertTrue(all(file.closed for session in (a, b) for file in session.files.values()))
        self.assertFalse(json.loads((self.capture.path / "manifest.json").read_text())["complete"])

    def test_disk_write_failure_marks_incomplete(self):
        session = self.capture.session()
        real = session.files["client_to_server"]
        session.files["client_to_server"] = Mock(wraps=real)
        session.files["client_to_server"].write.side_effect = OSError("disk full")
        with self.assertRaises(CaptureError):
            session.data("client_to_server", b"test")
        self.capture.close()
        self.assertFalse(json.loads((self.capture.path / "manifest.json").read_text())["complete"])

    def test_session_limit_marks_incomplete(self):
        self.capture.max_sessions = 1
        self.capture.session()
        with self.assertRaises(CaptureError):
            self.capture.session()
        self.assertTrue(self.capture.failed)


class RecordedMockTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = workspace_tempdir()
        self.capture = Capture(self.temp.name, "mock")
        self.mock = await MockPrinter(MockConfig(port=0), capture=self.capture).start()
        self.clients = []

    async def asyncTearDown(self):
        for reader, writer in self.clients:
            writer.close()
            await writer.wait_closed()
        await self.mock.close()
        self.capture.close()
        self.temp.cleanup()

    async def connect(self):
        pair = await asyncio.open_connection(*self.mock.address)
        self.clients.append(pair)
        return pair

    async def test_reported_second_m115_sequence_has_full_reply_history(self):
        request = b"~M601 S1\r\n~M115\r\n~M650\r\n~M115\r\n~M602\r\n"
        for _ in range(2):
            reader, writer = await self.connect()
            writer.write(request)
            writer.write_eof()
            reply = await asyncio.wait_for(reader.read(), 2)
            self.assertEqual(reply.count(b"CMD M115 Received."), 2)
            self.assertIn(b"X: 0 Y: 0", reply)
        await self.mock.close()
        self.capture.close()
        self.assertEqual(len(self.capture.sessions), 2)
        for session in self.capture.sessions:
            self.assertEqual(stream(self.capture, session.id, "client_to_server"), request)
            self.assertEqual(stream(self.capture, session.id, "server_to_client"), reply)
        log = (self.capture.path / "traffic.log").read_text()
        self.assertIn("s0001", log)
        self.assertIn("s0002", log)
        self.assertIn("server_to_client", log)

    async def test_partial_and_binary_input_recorded_before_parsing(self):
        reader, writer = await self.connect()
        writer.write(b"~M115\r\n\xffpartial")
        writer.write_eof()
        await asyncio.wait_for(reader.read(), 2)
        await self.mock.close()
        self.capture.close()
        self.assertEqual(stream(self.capture, "s0001", "client_to_server"), b"~M115\r\n\xffpartial")

    async def test_capture_failure_closes_client_without_reply(self):
        reader, writer = await self.connect()
        # Let connection registration finish, then exhaust the shared quota.
        writer.write(b"~M115\r\n")
        await asyncio.wait_for(reader.readuntil(b"ok\r\n"), 2)
        self.capture.max_bytes = self.capture.written
        writer.write(b"~M105\r\n")
        self.assertEqual(await asyncio.wait_for(reader.read(), 2), b"")
        self.assertTrue(self.capture.failed)
