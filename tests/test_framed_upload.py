"""Captured upload framing with synthetic payloads: no private model or hardware."""

import asyncio
import json
from pathlib import Path
import struct
import unittest
import zlib

from finderlab.protocol.upload import decode_frame
from finderlab.simulator import MockConfig, MockPrinter

REFERENCE = json.loads((Path(__file__).parent / "fixtures" / "finder-v1.5-upload.json").read_text())


def frame(index, data):
    # Construct independently of production decoding, using observed constants.
    return struct.pack("!4sIII", bytes.fromhex("5a5aa5a5"), index, len(data), zlib.crc32(data)) + data.ljust(4096, b"\x00")


class FrameTests(unittest.TestCase):
    def test_independent_known_crc32_vector(self):
        vector = REFERENCE["synthetic_crc_vector"]
        data = vector["payload_ascii"].encode()
        wire = bytes.fromhex(vector["header_hex"]) + data.ljust(4096, b"\x00")
        self.assertEqual(decode_frame(wire, 0, len(data)), data)

    def test_rejects_bad_size_magic_index_length_crc_and_padding(self):
        good = frame(0, b"123456789")
        mutations = [good[:-1], b"bad!" + good[4:]]
        for offset, value in ((7, 1), (11, 8), (15, good[15] ^ 1), (100, 1)):
            bad = bytearray(good)
            bad[offset] = value
            mutations.append(bytes(bad))
        for wire in mutations:
            with self.assertRaises(ValueError):
                decode_frame(wire, 0, 9)
        with self.assertRaises(ValueError):
            decode_frame(good, 0, 0)
        with self.assertRaises(ValueError):
            decode_frame(good, 0, 5000)  # Non-final blocks must carry 4096 bytes in this profile.


class FramedUploadTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.mock = await MockPrinter(MockConfig(port=0)).start()
        self.clients = []

    async def asyncTearDown(self):
        for _, writer in self.clients:
            writer.close()
            await writer.wait_closed()
        await self.mock.close()

    async def connect(self):
        pair = await asyncio.open_connection(*self.mock.address)
        self.clients.append(pair)
        return pair

    async def reply(self, pair):
        async def read():
            data = bytearray()
            while True:
                line = await pair[0].readline()
                self.assertTrue(line, "EOF before reply")
                data.extend(line)
                if line == b"ok\r\n" or line.startswith(b"Error:") or (line.startswith(b"N") and line.endswith(b" ok\r\n")):
                    return bytes(data)
        return await asyncio.wait_for(read(), 2)

    async def command(self, pair, command):
        pair[1].write(command.encode() + b"\r\n")
        await pair[1].drain()
        return await self.reply(pair)

    async def claim(self, pair):
        self.assertIn(b"Control Success.", await self.command(pair, "~M601 S1"))

    async def upload(self, pair, name, data):
        response = await self.command(pair, f"~M28 {len(data)} 0:/user/{name}")
        self.assertIn(f"Writing to file: 0:/user/{name}  Length: {len(data)}".encode(), response)
        for index, offset in enumerate(range(0, len(data), 4096)):
            wire = frame(index, data[offset:offset + 4096])
            # Fragment header/payload/padding independently of protocol boundaries.
            for start, end in ((0, 3), (3, 16), (16, 2037), (2037, len(wire))):
                pair[1].write(wire[start:end])
                await pair[1].drain()
            self.assertEqual(await self.reply(pair), f"N{index} ok\r\n".encode())
        self.assertNotIn(name, self.mock.files)
        self.assertEqual(await self.command(pair, "~M29"), REFERENCE["finish_reply"].encode())
        self.assertEqual(self.mock.files[name], data)
        return response

    async def test_default_profile_retains_captured_idle_bytes(self):
        idle = json.loads((Path(__file__).parent / "fixtures" / "finder-v1.5-idle.json").read_text())
        pair = await self.connect()
        for exchange in idle["exchanges"]:
            reply = await self.command(pair, exchange["request"].removesuffix("\r\n"))
            self.assertEqual(reply, exchange["reply"].encode())

    async def test_captured_size_and_ack_sequence_with_generated_payload(self):
        self.assertEqual(self.mock.profile.id, REFERENCE["profile_id"])
        pair = await self.connect()
        await self.claim(pair)
        data = bytes(i % 256 for i in range(REFERENCE["file_size"]))
        self.assertEqual(REFERENCE["frame_count"] * REFERENCE["frame_size"], REFERENCE["wire_range"][1] - REFERENCE["wire_range"][0])
        self.assertEqual(data[-REFERENCE["last_block_length"]:], data[25 * 4096:])
        response = await self.upload(pair, "test_box.gx", data)
        self.assertEqual(response, REFERENCE["begin_reply"].encode())
        self.assertIsNone(self.mock.active_file)  # M29 saves only; NEVER starts or cancels.
        self.assertIn(b"MachineStatus: READY", await self.command(pair, "~M119"))
        self.assertIn(b"T0:21 /0", await self.command(pair, "~M105"))

    async def test_larger_capture_size_with_spaces_and_same_framing(self):
        observed = REFERENCE["larger_transfer"]
        size = observed["file_size"]
        self.assertEqual((size + 4095) // 4096, observed["frame_count"])
        self.assertEqual(size % 4096, observed["last_block_length"])
        self.assertEqual(4096 - size % 4096, observed["final_padding_length"])
        self.assertEqual(observed["wire_range"][1] - observed["wire_range"][0], observed["frame_count"] * 4112)
        pair = await self.connect()
        await self.claim(pair)
        data = (bytes(range(256)) * ((size + 255) // 256))[:size]
        name = "large  sample - copy.gx"  # Generated name; double spaces must survive.
        await self.upload(pair, name, data)
        self.assertIsNone(self.mock.active_file)
        self.assertIn(b"Unknown virtual file", await self.command(pair, "~M23 0:/user/large sample - copy.gx"))
        self.assertIsNone(self.mock.active_file)
        self.assertEqual(
            await self.command(pair, f"~M23 0:/user/{name}"),
            f"CMD M23 Received.\r\nFile opened: 0:/user/{name} Size: {size}\r\nFile selected\r\nok\r\n".encode(),
        )
        self.assertEqual(self.mock.active_file, name)
        self.assertIn(b"BUILDING_FROM_SD", await self.command(pair, "~M119"))
        # Deliberately no M26: this new reference must not cause an implicit abort.

    async def test_spaced_names_do_not_allow_paths_or_control_characters(self):
        pair = await self.connect()
        await self.claim(pair)
        for name in (" leading.gx", "trailing.gx ", "a ../b.gx", "a /b.gx", "a \\b.gx", "a\tb.gx", "a\x00b.gx"):
            self.assertTrue((await self.command(pair, f"~M28 9 0:/user/{name}")).startswith(b"Error:"), repr(name))
        self.assertFalse(self.mock.files)
        self.assertIsNone(self.mock.active_file)
        # A rejected command must not enter payload mode or poison the session.
        await self.upload(pair, "valid sample.gx", b"123456789")

    async def test_captured_start_and_cancel_reply_frames(self):
        pair = await self.connect()
        await self.claim(pair)
        # Generated content, not a copy of the captured GX/model. Never executed.
        await self.upload(pair, "test_box.gx", b"X" * REFERENCE["file_size"])
        start = REFERENCE["start_request"].removesuffix("\r\n")
        self.assertEqual(await self.command(pair, start), REFERENCE["start_reply"].encode())
        self.assertEqual(self.mock.active_file, "test_box.gx")
        cancel = REFERENCE["cancel_request"].removesuffix("\r\n")
        self.assertEqual(await self.command(pair, cancel), REFERENCE["cancel_reply"].encode())
        self.assertIsNone(self.mock.active_file)
        self.assertIn("test_box.gx", self.mock.files)

    async def test_coalesced_frames_final_padding_m29_and_next_query(self):
        pair = await self.connect()
        await self.claim(pair)
        payload = bytes(range(256)) * 16 + b"\x00ok\r\n~M29\r\n~M26\r\n"
        await self.command(pair, f"~M28 {len(payload)} 0:/user/a.gx")
        wire = frame(0, payload[:4096]) + frame(1, payload[4096:])
        pair[1].write(wire + b"~M29\r\n~M119\r\n")
        self.assertEqual(await self.reply(pair), b"N0 ok\r\n")
        self.assertEqual(await self.reply(pair), b"N1 ok\r\n")
        self.assertEqual(await self.reply(pair), REFERENCE["finish_reply"].encode())
        self.assertIn(b"READY", await self.reply(pair))
        self.assertEqual(self.mock.files["a.gx"], payload)

    async def test_block_boundary_sizes(self):
        pair = await self.connect()
        await self.claim(pair)
        for size in (1, 4095, 4096, 4097, 8192):
            await self.upload(pair, f"n{size}.gx", b"A" * size)

    async def test_start_and_cancel_are_explicit_not_a_fixed_replay(self):
        pair = await self.connect()
        await self.claim(pair)
        await self.upload(pair, "a.gx", b"123456789")
        self.assertEqual(await self.command(pair, "~M23 0:/user/a.gx"), b"CMD M23 Received.\r\nFile opened: 0:/user/a.gx Size: 9\r\nFile selected\r\nok\r\n")
        for _ in range(12):
            self.assertIn(b"BUILDING_FROM_SD", await self.command(pair, "~M119"))
            self.assertIn(b"T0:21 /220", await self.command(pair, "~M105"))
            self.assertIn(b"SD printing byte 0/9", await self.command(pair, "~M27"))
        # Control release/disconnect must not implicitly cancel an active job.
        await self.command(pair, "~M602")
        pair[1].write_eof()
        self.assertEqual(await asyncio.wait_for(pair[0].read(), 2), b"")
        other = await self.connect()
        self.assertEqual(self.mock.active_file, "a.gx")
        self.assertIn(b"BUILDING_FROM_SD", await self.command(other, "~M119"))
        self.assertTrue((await self.command(other, "~M26")).startswith(b"Error:"))
        await self.claim(other)
        self.assertEqual(await self.command(other, "~M26"), REFERENCE["cancel_reply"].encode())
        self.assertIsNone(self.mock.active_file)
        self.assertIn(b"MachineStatus: READY", await self.command(other, "~M119"))
        self.assertIn(b"T0:21 /0", await self.command(other, "~M105"))
        self.assertEqual(self.mock.files["a.gx"], b"123456789")

    async def test_bad_frame_closes_and_preserves_old_file(self):
        first = await self.connect()
        await self.claim(first)
        await self.upload(first, "a.gx", b"old")
        await self.command(first, "~M28 9 0:/user/a.gx")
        broken = bytearray(frame(0, b"123456789"))
        broken[16] ^= 1
        first[1].write(broken)
        self.assertIn(b"Invalid upload CRC32", await self.reply(first))
        self.assertEqual(await asyncio.wait_for(first[0].read(), 2), b"")
        self.assertEqual(self.mock.files["a.gx"], b"old")
        await self.claim(await self.connect())

    async def test_incomplete_frame_discards_temporary_file(self):
        pair = await self.connect()
        await self.claim(pair)
        await self.command(pair, "~M28 9 0:/user/a.gx")
        pair[1].write(frame(0, b"123456789")[:25])  # Padding is part of the wire frame.
        pair[1].write_eof()
        self.assertEqual(await asyncio.wait_for(pair[0].read(), 2), b"")
        self.assertNotIn("a.gx", self.mock.files)
        self.assertIsNone(self.mock.active_file)

    async def test_busy_and_invalid_job_commands_do_not_cancel_job(self):
        pair = await self.connect()
        await self.claim(pair)
        self.assertIn(b"Unknown virtual file", await self.command(pair, "~M23 0:/user/missing.gx"))
        await self.upload(pair, "a.gx", b"abc")
        await self.command(pair, "~M23 0:/user/a.gx")
        for cmd in ("~M23 0:/user/a.gx", "~M28 1 0:/user/b.gx", "~M26 extra"):
            self.assertTrue((await self.command(pair, cmd)).startswith(b"Error:"))
            self.assertEqual(self.mock.active_file, "a.gx")
        self.assertNotIn("b.gx", self.mock.files)
