"""Independent de-identified printer-reference bytes, not synthetic client data."""

import asyncio
import json
from pathlib import Path
import unittest

from finderlab.simulator import MockConfig, MockPrinter

FIXTURE = Path(__file__).parent / "fixtures" / "finder-v1.5-idle.json"


class FinderProfileTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.reference = json.loads(FIXTURE.read_text())
        self.exchanges = self.reference["exchanges"]
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

    async def exchange(self, pair, request, expected):
        pair[1].write(request)
        await pair[1].drain()
        actual = await asyncio.wait_for(pair[0].readexactly(len(expected)), 2)
        self.assertEqual(actual, expected)

    async def test_captured_handshake_and_polling_prefix_byte_for_byte(self):
        self.assertEqual(self.mock.profile.id, self.reference["profile_id"])
        pair = await self.connect()
        for exchange in self.exchanges:
            await self.exchange(pair, exchange["request"].encode("ascii"), exchange["reply"].encode("ascii"))
        pair[1].write_eof()
        self.assertEqual(await asyncio.wait_for(pair[0].read(), 2), b"")
        self.assertFalse(self.mock.files)

    async def test_coalesced_capture_prefix_keeps_reply_order(self):
        pair = await self.connect()
        requests = "".join(e["request"] for e in self.exchanges).encode("ascii")
        replies = "".join(e["reply"] for e in self.exchanges).encode("ascii")
        self.assertEqual(len(requests), self.reference["source_client_range"][1])
        self.assertEqual(len(replies), self.reference["source_server_range"][1])
        await self.exchange(pair, requests, replies)
        pair[1].write_eof()
        self.assertEqual(await asyncio.wait_for(pair[0].read(), 2), b"")

    async def test_polling_is_stateful_not_a_fixed_replay_sequence(self):
        pair = await self.connect()
        replies = {e["request"]: e["reply"] for e in self.exchanges}
        # Repeated/reordered queries are accepted without a replay cursor.
        for command in ("M105", "M119", "M115", "M27", "M650", "M114") * 3:
            request = f"~{command}\r\n"
            await self.exchange(pair, request.encode(), replies[request].encode())
        await self.exchange(pair, b"~M601 S1\r\n", self.exchanges[0]["reply"].encode())
        # Release wasn't captured: retain the explicitly documented mock policy.
        await self.exchange(pair, b"~M602\r\n", b"CMD M602 Received.\r\nControl Release.\r\nok\r\n")
        await self.exchange(pair, b"~M601 S1\r\n", self.exchanges[0]["reply"].encode())

    async def test_experimental_upload_still_commits_only_after_m29(self):
        pair = await self.connect()
        await self.exchange(pair, b"~M601 S1\r\n", self.exchanges[0]["reply"].encode())
        payload = b"\x00\xff~M29\r\nok\r\n"
        await self.exchange(
            pair, f"~M28 {len(payload)} 0:/user/test.gx\r\n".encode(),
            b"CMD M28 Received.\r\nok\r\n",
        )
        self.assertFalse(self.mock.files)
        await self.exchange(pair, payload + b"~M29\r\n", b"CMD M29 Received.\r\nok\r\n")
        self.assertEqual(self.mock.files["test.gx"], payload)
        await self.exchange(pair, b"~M23 0:/user/test.gx\r\n", b"Error: Unsupported command (mock policy)\r\n")

    async def test_invalid_status_arguments_still_fail(self):
        pair = await self.connect()
        await self.exchange(pair, b"~M650 X1\r\n", b"Error: M650 takes no arguments\r\n")
        await self.exchange(pair, b"~M115 extra\r\n", b"Error: M115 takes no arguments\r\n")
