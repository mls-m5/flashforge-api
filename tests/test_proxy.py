"""Recording relay tests; targets are exclusively ephemeral localhost servers."""

import asyncio
import json
import unittest
from unittest.mock import patch

from finderlab.capture import Capture
from finderlab.proxy import ProxyConfig, RecordingProxy
from helpers import events, stream, workspace_tempdir


class ProxyTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = workspace_tempdir()
        self.capture = Capture(self.temp.name, "proxy")
        self.proxy = None
        self.upstream = None
        self.upstream_tasks = set()
        self.clients = []

    async def asyncTearDown(self):
        for _, writer in self.clients:
            writer.close()
            try:
                await writer.wait_closed()
            except ConnectionError:
                pass
        if self.proxy:
            await self.proxy.close()
        if self.upstream:
            self.upstream.close()
            await self.upstream.wait_closed()
        tasks = list(self.upstream_tasks)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        self.capture.close()
        self.temp.cleanup()

    async def start(self, handler, **options):
        async def serve(reader, writer):
            try:
                await handler(reader, writer)
            finally:
                writer.close()
                try:
                    await writer.wait_closed()
                except ConnectionError:
                    pass

        def accept(reader, writer):
            task = asyncio.create_task(serve(reader, writer))
            self.upstream_tasks.add(task)
            task.add_done_callback(self.upstream_tasks.discard)

        self.upstream = await asyncio.start_server(accept, "127.0.0.1", 0)
        target_port = self.upstream.sockets[0].getsockname()[1]
        self.proxy = await RecordingProxy(ProxyConfig(
            "127.0.0.1", target_port=target_port, port=0, **options,
        ), self.capture).start()

    async def connect(self):
        pair = await asyncio.open_connection(*self.proxy.address)
        self.clients.append(pair)
        return pair

    async def finish(self):
        await asyncio.wait_for(asyncio.gather(*list(self.proxy._tasks)), 3)

    async def test_half_close_and_exact_bidirectional_binary_streams(self):
        received = []
        request = bytes(range(256)) * 1000 + b"~M29\r\n"
        response = b"\x00\xffreply\r\nok\r\n"

        async def handler(reader, writer):
            received.append(await reader.read())
            writer.write(response)
            await writer.drain()

        await self.start(handler)
        reader, writer = await self.connect()
        for offset in range(0, len(request), 777):
            writer.write(request[offset:offset + 777])
            await writer.drain()
        writer.write_eof()
        self.assertEqual(await asyncio.wait_for(reader.read(), 3), response)
        await self.finish()
        self.assertEqual(received, [request])
        self.assertEqual(stream(self.capture, "s0001", "client_to_server"), request)
        self.assertEqual(stream(self.capture, "s0001", "server_to_client"), response)
        eofs = {e["direction"] for e in events(self.capture) if e["type"] == "eof"}
        self.assertEqual(eofs, {"client_to_server", "server_to_client"})
        data = {e["seq"] for e in events(self.capture) if e["type"] == "data"}
        forwarded = {e["data_seq"] for e in events(self.capture) if e["type"] == "forward_complete"}
        self.assertEqual(data, forwarded)

    async def test_simultaneous_large_streams_and_independent_connections(self):
        payload = bytes(range(256)) * 8192
        received = []

        async def handler(reader, writer):
            async def send():
                writer.write(payload)
                await writer.drain()
                writer.write_eof()
            async def receive():
                data = bytearray()
                while chunk := await reader.read(4096):
                    data.extend(chunk)
                    await asyncio.sleep(0)  # Deliberately slower receiver.
                received.append(bytes(data))
            await asyncio.gather(send(), receive())

        await self.start(handler)
        async def client():
            reader, writer = await self.connect()
            async def send():
                writer.write(payload)
                await writer.drain()
                writer.write_eof()
            async def receive():
                self.assertEqual(await reader.read(), payload)
            await asyncio.gather(send(), receive())
        await asyncio.wait_for(asyncio.gather(client(), client()), 10)
        await self.finish()
        # Relay completion means the bytes reached the target transport, not
        # that its deliberately slow application coroutine has consumed them.
        await asyncio.wait_for(asyncio.gather(*list(self.upstream_tasks)), 3)
        self.assertEqual(len(received), 2)
        for data in received:
            self.assertTrue(data == payload, "upstream payload mismatch")
        self.assertEqual(len(self.capture.sessions), 2)
        for record in self.capture.sessions:
            for direction in ("client_to_server", "server_to_client"):
                self.assertEqual(stream(self.capture, record.id, direction), payload)

    async def test_active_one_way_upload_does_not_time_out(self):
        async def handler(reader, writer):
            data = await reader.read()
            writer.write(data)
            await writer.drain()
        await self.start(handler, idle_timeout=0.2)
        reader, writer = await self.connect()
        for _ in range(6):
            writer.write(b"part")
            await writer.drain()
            await asyncio.sleep(0.05)  # Exercise an inactivity, not overall, timeout.
        writer.write_eof()
        self.assertEqual(await asyncio.wait_for(reader.read(), 2), b"part" * 6)
        await self.finish()

    async def test_idle_timeout_is_recorded(self):
        async def handler(reader, writer):
            await reader.read()
        await self.start(handler, idle_timeout=0.1)
        reader, _ = await self.connect()
        self.assertEqual(await asyncio.wait_for(reader.read(), 2), b"")
        await self.finish()
        self.assertTrue(any(e["type"] == "error" and e["error_type"] == "TimeoutError" for e in events(self.capture)))
        self.assertEqual(self.capture.sessions[0].summary["reason"], "timeout")

    async def test_connection_refusal_is_recorded_without_injected_reply(self):
        # Reserve a local port with a non-listening socket to ensure refusal.
        import socket
        with socket.socket() as reservation:
            reservation.bind(("127.0.0.1", 0))
            self.proxy = await RecordingProxy(ProxyConfig(
                "127.0.0.1", target_port=reservation.getsockname()[1], port=0,
            ), self.capture).start()
            reader, _ = await self.connect()
            self.assertEqual(await asyncio.wait_for(reader.read(), 2), b"")
            await self.finish()
        self.assertTrue(any(e["type"] == "error" and e["phase"] == "connect" for e in events(self.capture)))
        self.assertEqual(stream(self.capture, "s0001", "server_to_client"), b"")

    async def test_recording_failure_aborts_before_forwarding_new_data(self):
        received = []
        async def handler(reader, writer):
            writer.write(b"ready")
            await writer.drain()
            received.append(await reader.read())
        await self.start(handler)
        reader, writer = await self.connect()
        self.assertEqual(await asyncio.wait_for(reader.readexactly(5), 2), b"ready")
        self.capture.max_bytes = self.capture.written
        writer.write(b"must not forward")
        self.assertEqual(await asyncio.wait_for(reader.read(), 2), b"")
        await self.finish()
        await asyncio.gather(*list(self.upstream_tasks))
        self.assertEqual(received, [b""])
        self.capture.close()
        self.assertFalse(json.loads((self.capture.path / "manifest.json").read_text())["complete"])

    async def test_shutdown_closes_both_sides(self):
        async def handler(reader, writer):
            writer.write(b"ready")
            await writer.drain()
            await reader.read()
        await self.start(handler)
        reader, _ = await self.connect()
        self.assertEqual(await asyncio.wait_for(reader.readexactly(5), 2), b"ready")
        await asyncio.wait_for(self.proxy.close(), 2)
        self.assertEqual(await asyncio.wait_for(reader.read(), 2), b"")
        self.assertEqual(self.capture.sessions[0].summary["reason"], "server_shutdown")

    async def test_client_limit_keeps_existing_session_usable(self):
        async def handler(reader, writer):
            writer.write(b"ready")
            await writer.drain()
            writer.write(await reader.read())
            await writer.drain()
        await self.start(handler, max_clients=1)
        first_reader, first_writer = await self.connect()
        self.assertEqual(await asyncio.wait_for(first_reader.readexactly(5), 2), b"ready")
        second_reader, _ = await self.connect()
        self.assertEqual(await asyncio.wait_for(second_reader.read(), 2), b"")
        first_writer.write(b"still works")
        first_writer.write_eof()
        self.assertEqual(await asyncio.wait_for(first_reader.read(), 2), b"still works")
        await self.finish()
        self.assertEqual(len(self.capture.sessions), 1)

    async def test_connect_timeout_is_recorded(self):
        async def handler(reader, writer):
            await reader.read()
        await self.start(handler, connect_timeout=0.1)
        real_connect = asyncio.open_connection
        async def stalled_connect(*args, **kwargs):
            await asyncio.Future()
        with patch("finderlab.proxy.asyncio.open_connection", side_effect=stalled_connect):
            reader, writer = await real_connect(*self.proxy.address)
            self.clients.append((reader, writer))
            self.assertEqual(await asyncio.wait_for(reader.read(), 2), b"")
            await self.finish()
        self.assertTrue(any(e["type"] == "error" and e["phase"] == "connect"
                            and e["error_type"] == "TimeoutError" for e in events(self.capture)))

    async def test_obvious_self_target_rejected(self):
        # Port 0 avoids racing another process for a fixed test port.
        self.proxy = RecordingProxy(ProxyConfig("127.0.0.1", port=0), self.capture)
        await self.proxy.start()
        own_port = self.proxy.address[1]
        await self.proxy.close()
        self.proxy = RecordingProxy(ProxyConfig("127.0.0.1", port=own_port, target_port=own_port), self.capture)
        with self.assertRaisesRegex(ValueError, "loop"):
            await self.proxy.start()


class ProxyConfigTests(unittest.TestCase):
    def test_requires_explicit_ip_and_valid_limits(self):
        for values in (
            {"target_host": "printer.local"}, {"target_host": "127.0.0.1", "target_port": 0},
            {"target_host": "127.0.0.1", "idle_timeout": float("nan")},
            {"target_host": "127.0.0.1", "max_clients": 0},
        ):
            with self.assertRaises(ValueError):
                ProxyConfig(**values)
