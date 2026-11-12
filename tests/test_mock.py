"""Synthetic-only tests. Every socket connects to an ephemeral loopback port."""

import asyncio
from contextlib import redirect_stdout
import io
from pathlib import Path
import unittest
from unittest.mock import patch

from finderlab.__main__ import parser
from finderlab.simulator import MockConfig, MockPrinter
from helpers import workspace_tempdir
import upload


class MockTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        # Keep original synthetic semantics covered independently of the new default.
        self.printer = await MockPrinter(MockConfig(port=0, profile="synthetic-v1")).start()
        self.connections = []

    async def asyncTearDown(self):
        for _, writer in self.connections:
            writer.close()
            await writer.wait_closed()
        await self.printer.close()

    async def connect(self):
        pair = await asyncio.open_connection(*self.printer.address)
        self.connections.append(pair)
        return pair

    async def reply(self, reader):
        async def read():
            result = bytearray()
            while True:
                line = await reader.readline()
                if not line:
                    self.fail(f"EOF before reply finished: {result!r}")
                result.extend(line)
                if line == b"ok\r\n" or line.startswith(b"Error:"):
                    return bytes(result)
        return await asyncio.wait_for(read(), 2)

    async def command(self, pair, command):
        reader, writer = pair
        writer.write(command.encode("ascii") + b"\r\n")
        await writer.drain()
        return await self.reply(reader)

    async def claim(self, pair):
        self.assertIn(b"Control Success", await self.command(pair, "~M601 S1"))

    async def send_file(self, pair, name, data):
        self.assertIn(b"ok\r\n", await self.command(pair, f"~M28 {len(data)} 0:/user/{name}"))
        pair[1].write(data + b"~M29\r\n")
        await pair[1].drain()
        self.assertEqual(await self.reply(pair[0]), b"CMD M29 Received.\r\nok\r\n")

    async def test_identity_and_status(self):
        pair = await self.connect()
        info = await self.command(pair, "~M115")
        self.assertIn(b"Flashforge Finder 2", info)
        self.assertIn(b"synthetic-v1", info)
        for cmd in ("M105", "M114", "M119", "M27"):
            self.assertTrue((await self.command(pair, "~" + cmd)).endswith(b"ok\r\n"))
        self.assertIn(b"READY", await self.command(pair, "~M119"))

    async def test_reported_connection_sequence_with_m650(self):
        # User-reported incoming commands, not a capture of real-printer replies.
        pair = await self.connect()
        await self.claim(pair)
        self.assertIn(b"Machine Type:", await self.command(pair, "~M115"))
        self.assertEqual(
            await self.command(pair, "~M650"),
            b"CMD M650 Received.\r\nX: 0 Y: 0\r\nok\r\n",
        )
        self.assertIn(b"Control Release", await self.command(pair, "~M602"))
        # The mock stays usable; whether FlashPrint accepts the reply is unverified.
        self.assertIn(b"READY", await self.command(pair, "~M119"))
        await self.claim(await self.connect())

    async def test_m650_is_read_only_and_rejects_arguments(self):
        owner, observer = await self.connect(), await self.connect()
        await self.claim(owner)
        for _ in range(2):
            self.assertEqual(
                await self.command(observer, "~M650"),
                b"CMD M650 Received.\r\nX: 0 Y: 0\r\nok\r\n",
            )
        self.assertEqual(
            await self.command(observer, "~M650 X1"),
            b"Error: M650 takes no arguments\r\n",
        )
        # Querying offsets must neither acquire control nor modify storage.
        self.assertIn(b"Control Failed", await self.command(observer, "~M601 S1"))
        self.assertFalse(self.printer.files)
        await self.send_file(owner, "after-query.gx", b"abc")

    async def test_fragmented_and_coalesced_commands(self):
        reader, writer = await self.connect()
        for part in (b"~M", b"115\r", b"\n~M105\r\n~M27\r\n"):
            writer.write(part)
            await writer.drain()
        self.assertIn(b"Machine Type:", await self.reply(reader))
        self.assertIn(b"T0:", await self.reply(reader))
        self.assertIn(b"SD printing", await self.reply(reader))

    async def test_control_conflict_release_and_disconnect(self):
        a, b = await self.connect(), await self.connect()
        self.assertIn(b"Control required", await self.command(a, "~M28 1 0:/user/a.gx"))
        await self.claim(a)
        await self.claim(a)  # Idempotent claim by the same owner.
        self.assertIn(b"Control Failed", await self.command(b, "~M601 S1"))
        self.assertIn(b"another session", await self.command(b, "~M602"))
        self.assertIn(b"Control Release", await self.command(a, "~M602"))
        await self.claim(b)
        b[1].write_eof()
        self.assertEqual(await asyncio.wait_for(b[0].read(), 2), b"")
        await self.claim(a)

    async def test_exact_binary_payload_and_second_file(self):
        pair = await self.connect()
        await self.claim(pair)
        data = b"\x00\xffok\r\n~M29\r\n~M104 S200\r\n" + bytes(range(256)) * 300
        await self.send_file(pair, "one.gx", data)
        await self.send_file(pair, "two.gcode", b"G1 X0\n")
        self.assertEqual(self.printer.files["one.gx"], data)
        self.assertEqual(self.printer.files["two.gcode"], b"G1 X0\n")
        listing = await self.command(pair, "~M20")
        self.assertIn(f"one.gx {len(data)}".encode(), listing)
        self.assertIn(b"two.gcode 6", listing)
        self.assertIn(b"READY", await self.command(pair, "~M119"))
        with self.assertRaises(TypeError):
            self.printer.files["bad"] = b"test"

    async def test_upload_and_following_command_in_one_write(self):
        pair = await self.connect()
        pair[1].write(b"~M601 S1\r\n~M28 3 0:/user/a.gx\r\nabc~M29\r\n~M115\r\n")
        await pair[1].drain()
        for cmd in (b"M601", b"M28", b"M29", b"M115"):
            self.assertIn(b"CMD " + cmd, await self.reply(pair[0]))
        self.assertEqual(self.printer.files["a.gx"], b"abc")

    async def test_file_is_not_committed_before_m29_and_release_discards(self):
        pair = await self.connect()
        await self.claim(pair)
        await self.command(pair, "~M28 3 0:/user/a.gx")
        pair[1].write(b"abc~M105\r\n")
        self.assertIn(b"Upload pending", await self.reply(pair[0]))
        self.assertNotIn("a.gx", self.printer.files)
        await self.command(pair, "~M602")
        await self.claim(pair)
        self.assertIn(b"No upload pending", await self.command(pair, "~M29"))

    async def test_interrupted_upload_preserves_old_version(self):
        a = await self.connect()
        await self.claim(a)
        await self.send_file(a, "a.gx", b"old")
        await self.command(a, "~M28 5 0:/user/a.gx")
        a[1].write(b"ab")
        a[1].write_eof()
        self.assertEqual(await asyncio.wait_for(a[0].read(), 2), b"")
        self.assertEqual(self.printer.files["a.gx"], b"old")
        b = await self.connect()
        await self.claim(b)
        await self.send_file(b, "a.gx", b"new")
        self.assertEqual(self.printer.files["a.gx"], b"new")

    async def test_m29_missing_at_eof_discards_completed_payload(self):
        pair = await self.connect()
        await self.claim(pair)
        await self.command(pair, "~M28 3 0:/user/a.gx")
        pair[1].write(b"abc")
        pair[1].write_eof()
        self.assertEqual(await asyncio.wait_for(pair[0].read(), 2), b"")
        self.assertFalse(self.printer.files)

    async def test_rejects_bad_commands_without_success(self):
        pair = await self.connect()
        for cmd in ("M115", "~", "~M115 extra", "~M601", "~M104 S200", "~G28", "~M23 0:/user/a.gx"):
            reply = await self.command(pair, cmd)
            self.assertTrue(reply.startswith(b"Error:"), (cmd, reply))
            self.assertNotIn(b"ok\r\n", reply)
        pair[1].write(b"\xff\r\n~M115\r\n")
        self.assertIn(b"ASCII", await self.reply(pair[0]))
        self.assertIn(b"Machine Type:", await self.reply(pair[0]))

    async def test_rejects_invalid_sizes_and_paths(self):
        pair = await self.connect()
        await self.claim(pair)
        for args in (
            "0 0:/user/a.gx", "-1 0:/user/a.gx", "9999999999999 0:/user/a.gx",
            "8388609 0:/user/a.gx", "abc 0:/user/a.gx", "1 /outside/a.gx",
            "1 0:/user/../a.gx", "1 0:/user/a/b.gx", "1 0:/user/.hidden",
            "1 0:/user/a\\b.gx", "1 0:/user/a b.gx",
        ):
            self.assertTrue((await self.command(pair, "~M28 " + args)).startswith(b"Error:"), args)
        await self.send_file(pair, "valid.gx", b"x")

    async def restart(self, **overrides):
        await self.printer.close()
        self.printer = await MockPrinter(MockConfig(port=0, profile="synthetic-v1", **overrides)).start()

    async def test_storage_and_file_limits(self):
        await self.restart(max_file_size=4, storage_limit=6, max_files=2)
        pair = await self.connect()
        await self.claim(pair)
        await self.send_file(pair, "a.gx", b"1234")
        self.assertIn(b"Not enough space", await self.command(pair, "~M28 3 0:/user/b.gx"))
        await self.send_file(pair, "b.gx", b"12")
        self.assertIn(b"Too many", await self.command(pair, "~M28 1 0:/user/c.gx"))
        self.assertIn(b"Not enough space", await self.command(pair, "~M28 1 0:/user/a.gx"))
        self.assertEqual(self.printer.files["a.gx"], b"1234")

    async def test_overlong_line_is_closed(self):
        await self.restart(max_command_size=32)
        pair = await self.connect()
        pair[1].write(b"~" + b"A" * 64)
        self.assertIn(b"Command too long", await self.reply(pair[0]))
        self.assertEqual(await asyncio.wait_for(pair[0].read(), 2), b"")

    async def test_idle_timeout_releases_pending_upload(self):
        await self.restart(idle_timeout=0.1)
        pair = await self.connect()
        await self.claim(pair)
        await self.command(pair, "~M28 5 0:/user/a.gx")
        pair[1].write(b"a")
        self.assertEqual(await asyncio.wait_for(pair[0].read(), 2), b"")
        self.assertFalse(self.printer.files)
        await self.claim(await self.connect())

    async def test_client_limit(self):
        await self.restart(max_clients=1)
        first = await self.connect()
        await self.command(first, "~M115")
        second = await self.connect()
        self.assertEqual(await asyncio.wait_for(second[0].read(), 2), b"")
        self.assertIn(b"Machine Type:", await self.command(first, "~M115"))

    async def test_server_shutdown_closes_clients_and_discards_pending(self):
        pair = await self.connect()
        await self.claim(pair)
        await self.command(pair, "~M28 4 0:/user/a.gx")
        await self.printer.close()
        self.assertEqual(await asyncio.wait_for(pair[0].read(), 2), b"")
        self.assertFalse(self.printer.files)

    async def test_existing_upload_script_against_mock(self):
        # Patch only the destination port, not the uploader's parser or timing.
        with workspace_tempdir() as directory:
            path = Path(directory) / "sample.gx"
            data = b"; synthetic test file\n\x00\xff~M29\r\n"
            path.write_bytes(data)
            with patch.object(upload, "PORT", self.printer.address[1]), redirect_stdout(io.StringIO()):
                await asyncio.wait_for(asyncio.to_thread(upload.upload, "127.0.0.1", str(path)), 10)
            self.assertEqual(self.printer.files[path.name], data)


class ConfigTests(unittest.TestCase):
    def test_invalid_configuration(self):
        for kwargs in (
            {"port": -1}, {"port": 65536}, {"idle_timeout": 0},
            {"idle_timeout": float("nan")}, {"idle_timeout": float("inf")},
            {"max_file_size": 0}, {"storage_limit": -1}, {"max_clients": 0},
            {"max_files": 0}, {"max_command_size": 0}, {"profile": "unknown"},
        ):
            with self.assertRaises(ValueError, msg=str(kwargs)):
                MockConfig(**kwargs)

    def test_cli_defaults_and_overrides(self):
        defaults = parser().parse_args(["mock"])
        self.assertEqual(defaults.host, "127.0.0.1")
        self.assertEqual(defaults.port, 8899)
        self.assertEqual(defaults.profile, "finder-v1.5")
        custom = parser().parse_args(["mock", "--port", "0", "--max-files", "2", "--profile", "synthetic-v1"])
        self.assertEqual(custom.port, 0)
        self.assertEqual(custom.max_files, 2)
        self.assertEqual(custom.profile, "synthetic-v1")


if __name__ == "__main__":
    unittest.main()
