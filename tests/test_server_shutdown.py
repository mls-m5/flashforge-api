"""Owned loopback shutdown: exercise drain ordering even on Python3.11."""

import asyncio
from pathlib import Path
import unittest
from unittest.mock import patch

from finderlab.capture import Capture
from finderlab.proxy import ProxyConfig, RecordingProxy
from finderlab.simulator import MockConfig, MockPrinter
from finderlab.web import WebConfig, WebServer
from helpers import workspace_tempdir
from web_helpers import close_http_writer


class ServerShutdownTests(unittest.IsolatedAsyncioTestCase):
    async def assert_drained_before_wait(self, listener, tasks, close):
        active = list(tasks)
        self.assertTrue(active, "test must shut down an active handler")
        original = listener.wait_closed

        async def wait_closed():
            # Python3.12+ waits for accepted transports too. Assert ordering
            # rather than sleeping until the old30/60-second watchdog expires.
            self.assertTrue(all(task.done() for task in active),
                            "join active handlers before waiting for listener closure")
            await original()

        with patch.object(listener, "wait_closed", side_effect=wait_closed) as wait:
            await asyncio.wait_for(close(), 2)
            wait.assert_awaited_once()

    async def test_mock_shutdown_drains_active_session_before_listener(self):
        with workspace_tempdir() as directory:
            capture = Capture(directory, "mock")
            printer = await MockPrinter(MockConfig(port=0), capture=capture).start()
            reader, writer = await asyncio.open_connection(*printer.address)
            try:
                writer.write(b"~M115\r\n")
                await writer.drain()
                await asyncio.wait_for(reader.readuntil(b"ok\r\n"), 2)
                await self.assert_drained_before_wait(printer._server, printer._tasks, printer.close)
                self.assertEqual(await asyncio.wait_for(reader.read(), 2), b"")
                self.assertEqual(capture.sessions[0].summary["reason"], "server_shutdown")
            finally:
                writer.close()
                await writer.wait_closed()
                await printer.close()
                capture.close()

    async def test_proxy_shutdown_drains_both_sides_before_listener(self):
        with workspace_tempdir() as directory:
            capture = Capture(directory, "proxy")
            async with MockPrinter(MockConfig(port=0)) as printer:
                proxy = await RecordingProxy(ProxyConfig(
                    "127.0.0.1", target_port=printer.address[1], port=0,
                ), capture).start()
                reader, writer = await asyncio.open_connection(*proxy.address)
                try:
                    writer.write(b"~M115\r\n")
                    await writer.drain()
                    await asyncio.wait_for(reader.readuntil(b"ok\r\n"), 2)
                    upstream = list(printer._tasks)
                    self.assertTrue(upstream)
                    await self.assert_drained_before_wait(proxy._server, proxy._tasks, proxy.close)
                    self.assertEqual(await asyncio.wait_for(reader.read(), 2), b"")
                    await asyncio.wait_for(asyncio.gather(*upstream), 2)
                    self.assertEqual(capture.sessions[0].summary["reason"], "server_shutdown")
                finally:
                    writer.close()
                    await writer.wait_closed()
                    await proxy.close()
                    capture.close()

    async def test_web_shutdown_drains_incomplete_request_before_listener(self):
        with workspace_tempdir() as directory:
            server = await WebServer(WebConfig(port=0, data_dir=Path(directory))).__aenter__()
            entered = asyncio.Event()
            from finderlab.web import read_request

            async def reading(reader):
                entered.set()
                return await read_request(reader)

            with patch("finderlab.web.read_request", side_effect=reading), patch("finderlab.web.FinderClient") as client:
                reader, writer = await asyncio.open_connection(*server.address)
                try:
                    writer.write(b"GET / HTTP/1.1\r\n")
                    await writer.drain()
                    await asyncio.wait_for(entered.wait(), 2)
                    await self.assert_drained_before_wait(
                        server.server, server.clients, lambda: server.__aexit__(None, None, None),
                    )
                    # An incomplete HTTP request is aborted, not a promised
                    # graceful FIN. Both EOF and RST mean the socket is closed.
                    try:
                        self.assertEqual(await asyncio.wait_for(reader.read(), 2), b"")
                    except ConnectionResetError:
                        pass
                    client.assert_not_called()
                finally:
                    await close_http_writer(writer)
                    await server.__aexit__(None, None, None)
