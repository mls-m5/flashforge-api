"""Framed HTTP fixture responses survive RST only after a complete message."""

import asyncio
import socket
import struct
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

from web_helpers import WebTestCase, close_http_writer, read_http_response


class HttpFixtureCleanupTests(unittest.IsolatedAsyncioTestCase):
    def writer(self, error):
        return Mock(drain=AsyncMock(), wait_closed=AsyncMock(side_effect=error))

    def reader(self, response):
        reader = asyncio.StreamReader()
        reader.feed_data(response)
        reader.feed_eof()
        return reader

    async def request(self, reader, writer):
        context = SimpleNamespace(server=SimpleNamespace(
            authority="127.0.0.1:1", address=("127.0.0.1", 1), token="synthetic",
        ))
        with patch("web_helpers.asyncio.open_connection", new=AsyncMock(return_value=(reader, writer))):
            return await WebTestCase.request(context, "GET", "/api/state")

    async def test_complete_rejection_survives_reset_during_cleanup_only(self):
        body = b'{"error":"Client address is not allowed"}'
        response = b"HTTP/1.1 403 Forbidden\r\nContent-Length: " + str(len(body)).encode() + b"\r\n\r\n" + body
        writer = self.writer(ConnectionResetError("reset during close"))
        status, content = await self.request(self.reader(response), writer)
        self.assertEqual(status, 403)
        self.assertEqual(content, body)
        writer.close.assert_called_once()
        writer.wait_closed.assert_awaited_once()

    async def test_read_reset_is_not_hidden_or_replaced_by_cleanup_reset(self):
        reader = Mock(readuntil=AsyncMock(side_effect=ConnectionResetError("response read failed")))
        writer = self.writer(ConnectionResetError("cleanup reset"))
        with self.assertRaisesRegex(ConnectionResetError, "response read failed"):
            await self.request(reader, writer)
        writer.wait_closed.assert_awaited_once()

    async def test_incomplete_response_is_not_accepted_after_cleanup_reset(self):
        writer = self.writer(ConnectionResetError("cleanup reset"))
        with self.assertRaises(asyncio.IncompleteReadError):
            await self.request(self.reader(b"HTTP/1.1 403 incomplete"), writer)

    async def test_other_cleanup_errors_are_not_suppressed(self):
        for error in (TimeoutError("close timed out"), OSError("other I/O failure")):
            with self.subTest(error=type(error).__name__):
                writer = self.writer(error)
                with self.assertRaises(type(error)):
                    await close_http_writer(writer)

    async def test_missing_duplicate_invalid_or_oversized_lengths_are_not_accepted(self):
        for headers in (b"", b"Content-Length: 0\r\nContent-Length: 0\r\n",
                        b"Content-Length: -1\r\n", b"Content-Length: wrong\r\n",
                        b"Content-Length: 67108865\r\n"):
            with self.subTest(headers=headers), self.assertRaises(ValueError):
                await read_http_response(self.reader(b"HTTP/1.1 403 Forbidden\r\n" + headers + b"\r\n"))

    async def test_truncated_body_and_oversized_headers_fail(self):
        with self.assertRaises(asyncio.IncompleteReadError):
            await read_http_response(self.reader(b"HTTP/1.1 403 Forbidden\r\nContent-Length: 3\r\n\r\n{}"))
        with self.assertRaises(ValueError):
            await read_http_response(self.reader(b"HTTP/1.1 403 Forbidden\r\nX: " + b"x" * 16384 + b"\r\nContent-Length: 0\r\n\r\n"))

    async def reset_exchange(self, response, *, raw=False):
        async def reject(reader, writer):
            head, body = response.split(b"\r\n\r\n", 1)
            writer.write(head + b"\r\n\r\n")
            await asyncio.wait_for(writer.drain(), 1)
            writer.write(body)
            await asyncio.wait_for(writer.drain(), 1)
            # Deterministic Linux TCP RST after the supplied bytes, without a
            # printer, proxy, timing sleep or changes to production access gates.
            writer.get_extra_info("socket").setsockopt(
                socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0),
            )
            writer.transport.abort()

        server = await asyncio.start_server(reject, "127.0.0.1", 0)
        address = server.sockets[0].getsockname()[:2]
        target = SimpleNamespace(authority=f"{address[0]}:{address[1]}", address=address, token="synthetic")
        try:
            if raw:
                from test_web_http_integration import WebHttpIntegrationTests
                self.server = target
                return await WebHttpIntegrationTests.raw_request(self, b"not HTTP\r\n\r\n")
            return await WebTestCase.request(SimpleNamespace(server=target), "GET", "/api/state")
        finally:
            server.close()
            await server.wait_closed()

    @unittest.skipUnless(sys.platform.startswith("linux"), "Linux SO_LINGER reset fixture")
    async def test_real_tcp_reset_after_complete_reply_preserves_both_fixture_responses(self):
        response = (b"HTTP/1.1 403 Forbidden\r\nContent-Length: 2\r\nConnection: close\r\n"
                    b"Content-Security-Policy: default-src 'none'\r\n\r\n{}")
        for raw in (False, True):
            with self.subTest(raw=raw):
                status, body = await self.reset_exchange(response, raw=raw)
                self.assertEqual(status, 403)
                self.assertEqual(body, {} if raw else b"{}")

    @unittest.skipUnless(sys.platform.startswith("linux"), "Linux SO_LINGER reset fixture")
    async def test_real_tcp_reset_before_complete_body_is_not_hidden(self):
        with self.assertRaises(ConnectionResetError):
            await self.reset_exchange(b"HTTP/1.1 403 Forbidden\r\nContent-Length: 9\r\n\r\n{}")
