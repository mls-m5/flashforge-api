"""Exercise real CLI lifecycle; captures and tool temp storage stay in .tmp/."""

import asyncio
import json
import os
from pathlib import Path
import signal
import sys
import unittest

from finderlab.simulator import MockConfig, MockPrinter
from helpers import workspace_tempdir


@unittest.skipUnless(os.name == "posix", "CLI Ctrl+C lifecycle uses POSIX signals")
class CLITests(unittest.IsolatedAsyncioTestCase):
    async def test_upload_cli_is_upload_only_and_records_history(self):
        root = Path(__file__).resolve().parents[1]
        with workspace_tempdir() as directory:
            path = Path(directory) / "CLI thumbnail sample.gx"
            payload = b"synthetic GX test only\x00BM\x00\xff" + bytes(range(256)) * 20
            path.write_bytes(payload)
            async with MockPrinter(MockConfig(port=0)) as mock:
                process = await asyncio.create_subprocess_exec(
                    sys.executable, "-m", "finderlab", "upload", str(path),
                    "--port", str(mock.address[1]), "--capture-dir", directory,
                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                    cwd=root, env={**os.environ, "TMPDIR": str(root / ".tmp")},
                )
                try:
                    stdout, stderr = await asyncio.wait_for(process.communicate(), 8)
                    self.assertEqual(process.returncode, 0, stderr.decode())
                    self.assertEqual(stderr, b"")
                    self.assertIn(b"Save confirmed:", stdout)
                    self.assertEqual(mock.files[path.name], payload)
                    self.assertIsNone(mock.active_file)
                    manifest_path = next(Path(directory).glob("*/manifest.json"))
                    manifest = json.loads(manifest_path.read_text())
                    self.assertEqual(manifest["mode"], "client")
                    self.assertEqual(manifest["metadata"]["operation"], "upload")
                    self.assertTrue(manifest["complete"])
                    self.assertEqual(len(manifest["sessions"]), 1)
                finally:
                    if process.returncode is None:
                        process.kill()
                        await process.communicate()

    async def test_job_confirmations_and_hardware_guard_fail_before_connect(self):
        root = Path(__file__).resolve().parents[1]
        with workspace_tempdir() as directory:
            for arguments in (("start", "sample.gx"), ("stop",), ("status", "--host", "192.0.2.10")):
                process = await asyncio.create_subprocess_exec(
                    sys.executable, "-m", "finderlab", *arguments, "--capture-dir", directory,
                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                    cwd=root, env={**os.environ, "TMPDIR": str(root / ".tmp")},
                )
                stdout, stderr = await asyncio.wait_for(process.communicate(), 5)
                self.assertEqual(process.returncode, 2, stderr.decode())
                self.assertNotIn(b"Target:", stdout)
            self.assertFalse(list(Path(directory).iterdir()))

    async def test_proxy_cli_records_local_mock_replies(self):
        root = Path(__file__).resolve().parents[1]
        with workspace_tempdir() as directory:
            async with MockPrinter(MockConfig(port=0)) as mock:
                process = await asyncio.create_subprocess_exec(
                    sys.executable, "-m", "finderlab", "proxy", "--port", "0",
                    "--target-host", "127.0.0.1", "--target-port", str(mock.address[1]),
                    "--capture-dir", directory,
                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                    cwd=root, env={**os.environ, "TMPDIR": str(root / ".tmp")},
                )
                try:
                    line = await asyncio.wait_for(process.stdout.readline(), 5)
                    port = int(line.decode().strip().rsplit(":", 1)[1])
                    reader, writer = await asyncio.open_connection("127.0.0.1", port)
                    writer.write(b"~M115\r\n")
                    writer.write_eof()
                    reply = await asyncio.wait_for(reader.read(), 2)
                    self.assertIn(b"Firmware: V1.5 20170419", reply)
                    writer.close()
                    await writer.wait_closed()
                    process.send_signal(signal.SIGINT)
                    _, stderr = await asyncio.wait_for(process.communicate(), 5)
                    self.assertEqual(process.returncode, 0, stderr.decode())
                    self.assertEqual(stderr, b"")
                    manifest_path = next(Path(directory).glob("*/manifest.json"))
                    manifest = json.loads(manifest_path.read_text())
                    self.assertEqual(manifest["mode"], "proxy")
                    self.assertTrue(manifest["complete"])
                    session = manifest_path.parent / "sessions" / "s0001"
                    self.assertEqual((session / "client-to-server.bin").read_bytes(), b"~M115\r\n")
                    self.assertEqual((session / "server-to-client.bin").read_bytes(), reply)
                finally:
                    if process.returncode is None:
                        process.kill()
                        await process.communicate()

    async def test_default_recording_and_history_survive_restart(self):
        with workspace_tempdir() as directory:
            root = Path(__file__).resolve().parents[1]
            env = {**os.environ, "TMPDIR": str(root / ".tmp")}
            for _ in range(2):
                process = await asyncio.create_subprocess_exec(
                    sys.executable, "-m", "finderlab", "mock", "--port", "0",
                    "--capture-dir", directory, "--flashprint-version", "test-client",
                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                    cwd=root, env=env,
                )
                try:
                    line = await asyncio.wait_for(process.stdout.readline(), 5)
                    port = int(line.decode().strip().rsplit(":", 1)[1])
                    capture_line = await asyncio.wait_for(process.stdout.readline(), 2)
                    self.assertIn(b"Capture directory:", capture_line)
                    manifest_path = next(path for path in Path(directory).glob("*/manifest.json")
                                         if not json.loads(path.read_text())["complete"])
                    active = json.loads(manifest_path.read_text())
                    self.assertEqual(active["flashprint_version"], "test-client")
                    self.assertEqual(active["firmware"], "V1.5 20170419")
                    self.assertEqual(active["metadata"]["profile"], "finder-v1.5")
                    self.assertEqual(active["metadata"]["profile_source_capture"], "20261112T191450Z-2b04f784b894")
                    reader, writer = await asyncio.open_connection("127.0.0.1", port)
                    writer.write(b"~M115\r\n")
                    self.assertIn(b"Firmware: V1.5 20170419", await asyncio.wait_for(reader.readuntil(b"ok\r\n"), 2))
                    writer.write_eof()
                    await asyncio.wait_for(reader.read(), 2)
                    writer.close()
                    await writer.wait_closed()
                    process.send_signal(signal.SIGINT)
                    _, stderr = await asyncio.wait_for(process.communicate(), 5)
                    self.assertEqual(process.returncode, 0, stderr.decode())
                    self.assertEqual(stderr, b"")
                    self.assertTrue(json.loads(manifest_path.read_text())["complete"])
                finally:
                    if process.returncode is None:
                        process.kill()
                        await process.communicate()
            manifests = list(Path(directory).glob("*/manifest.json"))
            self.assertEqual(len(manifests), 2)
            for path in manifests:
                self.assertTrue((path.parent / "traffic.log").exists())
                self.assertEqual(len(json.loads(path.read_text())["sessions"]), 1)
