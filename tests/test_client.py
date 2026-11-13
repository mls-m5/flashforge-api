"""Client tests against independent scripted reference replies and local mock."""

import asyncio
import hashlib
import json
import os
from pathlib import Path
import sys
import unittest

from finderlab.client import ClientConfig, ClientError, FinderClient, ResultUnknown, remote_path
from finderlab.protocol.upload import encode_frame
from finderlab.simulator import MockConfig, MockPrinter
from helpers import workspace_tempdir

FIXTURES = Path(__file__).parent / "fixtures"
IDLE = json.loads((FIXTURES / "finder-v1.5-idle.json").read_text())
UPLOAD = json.loads((FIXTURES / "finder-v1.5-upload.json").read_text())
REPLIES = {x["request"]: x["reply"].encode() for x in IDLE["exchanges"]}
RELEASE = (b"~M602\r\n", b"CMD M602 Received.\r\nControl Release.\r\nok\r\n")
VECTOR = UPLOAD["synthetic_crc_vector"]
PAYLOAD = VECTOR["payload_ascii"].encode()
WIRE = bytes.fromhex(VECTOR["header_hex"]) + PAYLOAD.ljust(4096, b"\x00")


class EncodingTests(unittest.TestCase):
    def test_encoder_matches_independent_fixture_vector(self):
        self.assertEqual(encode_frame(0, PAYLOAD), WIRE)
        for index, data in ((-1, b"x"), (0x100000000, b"x"), (0, b""), (0, b"x" * 4097)):
            with self.assertRaises(ValueError):
                encode_frame(index, data)

    def test_target_guard_and_remote_names(self):
        with self.assertRaises(ValueError):
            ClientConfig(host="192.0.2.10")
        with self.assertRaises(ValueError):
            ClientConfig(host="printer.local", allow_hardware=True)
        self.assertEqual(ClientConfig(host="192.0.2.10", allow_hardware=True).port, 8899)
        self.assertEqual(remote_path("a  sample - copy.gx"), "0:/user/a  sample - copy.gx")
        for name in ("sample.gcode", "sample.GCODE", "sample.g", "sample.GX"):
            self.assertEqual(remote_path(name), "0:/user/" + name)
        for name in ("../a.gx", "a\nb.gx", " a.gx", "a.gx ", "ä.gx", "a/b.gx", "file.stl", "file.bgcode", "file.3mf"):
            with self.assertRaises(ValueError, msg=name):
                remote_path(name)
        for kwargs in ({"timeout": 0}, {"timeout": float("nan")}, {"port": 0}, {"max_file_size": 0}):
            with self.assertRaises(ValueError):
                ClientConfig(**kwargs)


class ScriptedClientTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = workspace_tempdir()
        self.path = Path(self.temp.name) / "test_box.gx"
        self.path.write_bytes(PAYLOAD)
        self.server = None
        self.tasks = set()
        self.errors = []
        self.trailing = []
        self.requests = []

    async def asyncTearDown(self):
        if self.server:
            self.server.close()
            await self.server.wait_closed()
        tasks = list(self.tasks)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        self.temp.cleanup()
        self.assertEqual(self.errors, [])

    def handshake(self):
        return [(command.encode(), REPLIES[command]) for command in ("~M601 S1\r\n", "~M115\r\n")]

    def begin(self):
        return (b"~M28 9 0:/user/test_box.gx\r\n", UPLOAD["begin_reply"].replace("102989", "9").encode())

    async def serve(self, steps, *, fragment=False, timeout=1.0):
        async def handler(reader, writer):
            try:
                for request, reply in steps:
                    actual = await asyncio.wait_for(reader.readexactly(len(request)), 3)
                    self.assertEqual(actual, request)
                    self.requests.append(actual)
                    if callable(reply):
                        await reply(reader, writer)
                        continue
                    if fragment:
                        for i in range(0, len(reply), 3):
                            writer.write(reply[i:i + 3])
                            await writer.drain()
                            await asyncio.sleep(0)
                    else:
                        writer.write(reply)
                        await writer.drain()
                writer.write_eof()
                self.trailing.append(await asyncio.wait_for(reader.read(), 3))
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.errors.append(str(exc))
            finally:
                writer.close()
                try:
                    await writer.wait_closed()
                except ConnectionError:
                    pass

        def accept(reader, writer):
            task = asyncio.create_task(handler(reader, writer))
            self.tasks.add(task)
            task.add_done_callback(self.tasks.discard)
        self.server = await asyncio.start_server(accept, "127.0.0.1", 0)
        return ClientConfig(port=self.server.sockets[0].getsockname()[1], timeout=timeout, save_timeout=timeout)

    async def finished(self):
        await asyncio.wait_for(asyncio.gather(*list(self.tasks)), 4)
        self.assertTrue(all(data == b"" for data in self.trailing), "Unexpected trailing cleanup/job commands")

    async def upload_cli(self, config):
        root = Path(__file__).resolve().parents[1]
        capture_dir = Path(self.temp.name) / "cli-captures"
        process = await asyncio.create_subprocess_exec(
            sys.executable, "-m", "finderlab", "upload", str(self.path), "--start",
            "--port", str(config.port), "--capture-dir", str(capture_dir),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            cwd=root, env={**os.environ, "TMPDIR": str(root / ".tmp")},
        )
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), 6)
        finally:
            if process.returncode is None:
                process.kill()
                await process.communicate()
        await self.finished()
        manifest = json.loads(next(capture_dir.glob("*/manifest.json")).read_text())
        return process.returncode, stdout, stderr, manifest

    async def test_upload_start_flag_never_starts_after_wrong_ack(self):
        config = await self.serve(self.handshake() + [(b"~M119\r\n", REPLIES["~M119\r\n"]), self.begin(), (WIRE, b"N1 ok\r\n")])
        code, stdout, stderr, manifest = await self.upload_cli(config)
        self.assertEqual(code, 1)
        self.assertNotIn(b"Start acknowledged", stdout)
        self.assertIn(b"Expected block ACK N0", stderr)
        self.assertTrue(manifest["metadata"]["start_requested"])
        self.assertNotIn("upload_confirmed", manifest["metadata"])
        self.assertNotIn(b"~M23 0:/user/test_box.gx\r\n", self.requests)

    async def test_upload_start_flag_never_starts_after_unknown_save(self):
        steps = self.handshake() + [(b"~M119\r\n", REPLIES["~M119\r\n"]), self.begin(), (WIRE, b"N0 ok\r\n"),
                                    (b"~M29\r\n", b"CMD M29 Received.\r\nDone saving file.\r\nok")]
        config = await self.serve(steps)
        code, stdout, stderr, manifest = await self.upload_cli(config)
        self.assertEqual(code, 1)
        self.assertNotIn(b"Start acknowledged", stdout)
        self.assertIn(b"result UNKNOWN", stderr)
        self.assertNotIn("upload_confirmed", manifest["metadata"])
        self.assertNotIn(b"~M23 0:/user/test_box.gx\r\n", self.requests)

    async def test_upload_start_rechecks_ready_without_cancelling_other_work(self):
        busy = REPLIES["~M119\r\n"].replace(b"MachineStatus: READY", b"MachineStatus: BUILDING_FROM_SD")
        steps = self.handshake() + [(b"~M119\r\n", REPLIES["~M119\r\n"]), self.begin(), (WIRE, b"N0 ok\r\n"),
                                    (b"~M29\r\n", UPLOAD["finish_reply"].encode()), (b"~M119\r\n", busy), RELEASE]
        config = await self.serve(steps)
        code, stdout, stderr, manifest = await self.upload_cli(config)
        self.assertEqual(code, 1)
        self.assertIn(b"Save confirmed:", stdout)
        self.assertIn(b"not READY", stderr)
        self.assertTrue(manifest["metadata"]["upload_confirmed"])
        self.assertNotIn("start_acknowledged", manifest["metadata"])
        self.assertNotIn(b"~M23 0:/user/test_box.gx\r\n", self.requests)
        self.assertNotIn(b"~M26\r\n", self.requests)

    async def test_upload_start_failure_keeps_save_confirmation_and_does_not_retry(self):
        steps = self.handshake() + [(b"~M119\r\n", REPLIES["~M119\r\n"]), self.begin(), (WIRE, b"N0 ok\r\n"),
                                    (b"~M29\r\n", UPLOAD["finish_reply"].encode()),
                                    (b"~M119\r\n", REPLIES["~M119\r\n"]), (b"~M23 0:/user/test_box.gx\r\n", b"")]
        config = await self.serve(steps)
        code, stdout, stderr, manifest = await self.upload_cli(config)
        self.assertEqual(code, 1)
        self.assertIn(b"Save confirmed:", stdout)
        self.assertIn(b"job state UNKNOWN", stderr)
        self.assertTrue(manifest["metadata"]["upload_confirmed"])
        self.assertNotIn("start_acknowledged", manifest["metadata"])
        self.assertEqual(self.requests.count(WIRE), 1)
        self.assertEqual(self.requests.count(b"~M23 0:/user/test_box.gx\r\n"), 1)

    async def test_exact_captured_reply_formats_and_independent_wire_vector(self):
        steps = self.handshake() + [(b"~M119\r\n", REPLIES["~M119\r\n"]), self.begin(),
                                    (WIRE, b"N0 ok\r\n"), (b"~M29\r\n", UPLOAD["finish_reply"].encode()), RELEASE]
        config = await self.serve(steps, fragment=True)
        progress = []
        async with FinderClient(config) as client:
            result = await client.upload(self.path, progress=lambda sent, total: progress.append((sent, total)))
        self.assertEqual(result.size, 9)
        self.assertEqual(result.sha256, hashlib.sha256(PAYLOAD).hexdigest())
        self.assertEqual(progress, [(9, 9)])
        await self.finished()

    async def test_wrong_ack_never_retries_commits_or_injects_release(self):
        config = await self.serve(self.handshake() + [(b"~M119\r\n", REPLIES["~M119\r\n"]), self.begin(), (WIRE, b"N1 ok\r\n")])
        async with FinderClient(config) as client:
            with self.assertRaisesRegex(ClientError, "Expected block ACK N0"):
                await client.upload(self.path)
            with self.assertRaisesRegex(ClientError, "Session is not ready"):
                await client.status()
        await self.finished()
        self.assertEqual(self.requests.count(WIRE), 1)

    async def test_lost_final_newline_means_unknown_not_success(self):
        steps = self.handshake() + [(b"~M119\r\n", REPLIES["~M119\r\n"]), self.begin(), (WIRE, b"N0 ok\r\n"),
                                    (b"~M29\r\n", b"CMD M29 Received.\r\nDone saving file.\r\nok")]
        config = await self.serve(steps)
        async with FinderClient(config) as client:
            with self.assertRaisesRegex(ResultUnknown, "save was not confirmed"):
                await client.upload(self.path)
        await self.finished()

    async def test_error_plus_ok_is_never_success(self):
        steps = self.handshake() + [(b"~M119\r\n", REPLIES["~M119\r\n"]),
                                    (self.begin()[0], b"CMD M28 Received.\r\nError: no space\r\nok\r\n")]
        config = await self.serve(steps)
        async with FinderClient(config) as client:
            with self.assertRaisesRegex(ClientError, "no space"):
                await client.upload(self.path)
        await self.finished()

    async def test_release_failure_does_not_unconfirm_or_retry_saved_file(self):
        steps = self.handshake() + [(b"~M119\r\n", REPLIES["~M119\r\n"]), self.begin(),
                                    (WIRE, b"N0 ok\r\n"), (b"~M29\r\n", UPLOAD["finish_reply"].encode()),
                                    (RELEASE[0], b"Error: release failed\r\n")]
        config = await self.serve(steps)
        async with FinderClient(config) as client:
            result = await client.upload(self.path)
        self.assertEqual(result.size, 9)
        self.assertIsNotNone(client.cleanup_error)
        self.assertEqual(self.requests.count(WIRE), 1)
        await self.finished()

    async def test_wrong_command_echo_is_rejected_even_with_ok(self):
        steps = [self.handshake()[0], (b"~M115\r\n", b"CMD M650 Received.\r\nX: 34 Y: 0\r\nok\r\n")]
        config = await self.serve(steps)
        with self.assertRaisesRegex(ClientError, "Unexpected command reply"):
            async with FinderClient(config):
                self.fail("Wrong command reply was accepted")
        await self.finished()

    async def test_busy_printer_is_not_cancelled_or_uploaded_to(self):
        busy = REPLIES["~M119\r\n"].replace(b"MachineStatus: READY", b"MachineStatus: BUILDING_FROM_SD")
        config = await self.serve(self.handshake() + [(b"~M119\r\n", busy), RELEASE])
        async with FinderClient(config) as client:
            with self.assertRaisesRegex(ClientError, "not READY"):
                await client.upload(self.path)
        await self.finished()

    async def test_changed_source_is_not_committed(self):
        config = await self.serve(self.handshake() + [(b"~M119\r\n", REPLIES["~M119\r\n"]), self.begin(), (WIRE, b"N0 ok\r\n")])
        async with FinderClient(config) as client:
            with self.assertRaisesRegex(ClientError, "Source file changed"):
                await client.upload(self.path, progress=lambda *_: self.path.write_bytes(b"changed"))
        await self.finished()

    async def test_cancel_during_binary_upload_closes_without_commands(self):
        received = asyncio.Event()
        async def no_ack(reader, writer):
            received.set()
            self.trailing.append(await reader.read())  # Wait for cancellation to close the client.
        config = await self.serve(self.handshake() + [(b"~M119\r\n", REPLIES["~M119\r\n"]), self.begin(), (WIRE, no_ack)])
        async def upload():
            async with FinderClient(config) as client:
                await client.upload(self.path)
        task = asyncio.create_task(upload())
        await asyncio.wait_for(received.wait(), 2)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        await self.finished()

    async def test_block_reply_timeout_does_not_retry(self):
        async def no_reply(reader, writer):
            await asyncio.sleep(0.2)
        config = await self.serve(self.handshake() + [(b"~M119\r\n", REPLIES["~M119\r\n"]), self.begin(), (WIRE, no_reply)], timeout=0.1)
        async with FinderClient(config) as client:
            with self.assertRaisesRegex(ClientError, "interrupted"):
                await client.upload(self.path)
        await self.finished()


class MockClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_supported_formats_are_preserved_without_conversion_or_start(self):
        with workspace_tempdir() as directory:
            async with MockPrinter(MockConfig(port=0)) as mock:
                async with FinderClient(ClientConfig(port=mock.address[1])) as client:
                    for suffix in (".gx", ".GCODE", ".g"):
                        path = Path(directory) / ("sample" + suffix)
                        data = b"; test only\r\nG90\nG1 X1 Y1\n" + suffix.encode()
                        path.write_bytes(data)
                        result = await client.upload(path)
                        self.assertEqual(result.path, "0:/user/" + path.name)
                        self.assertEqual(mock.files[path.name], data)
                        self.assertEqual(result.sha256, hashlib.sha256(data).hexdigest())
                        self.assertIsNone(mock.active_file)

    async def test_upload_preserves_gx_bytes_and_actions_are_separate(self):
        with workspace_tempdir() as directory:
            path = Path(directory) / "binary thumbnail sample.gx"
            data = b"xgcode synthetic test only\x00BM\x00\xff" + bytes(range(256)) * 40 + b"~M23\r\n~M26\r\n"
            path.write_bytes(data)
            async with MockPrinter(MockConfig(port=0)) as mock:
                config = ClientConfig(port=mock.address[1])
                async with FinderClient(config) as client:
                    result = await client.upload(path)
                    self.assertEqual(mock.files[path.name], data)
                    self.assertEqual(result.sha256, hashlib.sha256(data).hexdigest())
                    self.assertIsNone(mock.active_file)
                    with self.assertRaises(ValueError):
                        await client.start(path.name)
                    await client.start(path.name, confirm=True)
                    self.assertEqual(mock.active_file, path.name)
                self.assertEqual(mock.active_file, path.name)  # M602/close is NOT a stop.
                async with FinderClient(config) as client:
                    status = await client.status()
                    self.assertIn(b"MachineStatus: BUILDING_FROM_SD", status["M119"])
                    with self.assertRaises(ValueError):
                        await client.stop()
                    self.assertEqual(mock.active_file, path.name)
                    await client.stop(confirm=True)
                    self.assertIsNone(mock.active_file)
