"""HTTP fixture cleanup must not turn a complete rejection into a TCP error."""

from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

from web_helpers import WebTestCase, close_http_writer


class HttpFixtureCleanupTests(unittest.IsolatedAsyncioTestCase):
    def writer(self, error):
        return Mock(drain=AsyncMock(), wait_closed=AsyncMock(side_effect=error))

    async def request(self, reader, writer):
        context = SimpleNamespace(server=SimpleNamespace(
            authority="127.0.0.1:1", address=("127.0.0.1", 1), token="synthetic",
        ))
        with patch("web_helpers.asyncio.open_connection", new=AsyncMock(return_value=(reader, writer))):
            return await WebTestCase.request(context, "GET", "/api/state")

    async def test_complete_rejection_survives_reset_during_cleanup_only(self):
        body = b'{"error":"Client address is not allowed"}'
        response = b"HTTP/1.1 403 Forbidden\r\nContent-Length: " + str(len(body)).encode() + b"\r\n\r\n" + body
        reader = Mock(read=AsyncMock(return_value=response))
        writer = self.writer(ConnectionResetError("reset during close"))
        status, content = await self.request(reader, writer)
        self.assertEqual(status, 403)
        self.assertEqual(content, body)
        reader.read.assert_awaited_once()
        writer.close.assert_called_once()
        writer.wait_closed.assert_awaited_once()

    async def test_read_reset_is_not_hidden_or_replaced_by_cleanup_reset(self):
        reader = Mock(read=AsyncMock(side_effect=ConnectionResetError("response read failed")))
        writer = self.writer(ConnectionResetError("cleanup reset"))
        with self.assertRaisesRegex(ConnectionResetError, "response read failed"):
            await self.request(reader, writer)
        writer.wait_closed.assert_awaited_once()

    async def test_incomplete_response_is_not_accepted_after_cleanup_reset(self):
        reader = Mock(read=AsyncMock(return_value=b"HTTP/1.1 403 incomplete"))
        writer = self.writer(ConnectionResetError("cleanup reset"))
        with self.assertRaises(ValueError):
            await self.request(reader, writer)

    async def test_other_cleanup_errors_are_not_suppressed(self):
        for error in (TimeoutError("close timed out"), OSError("other I/O failure")):
            with self.subTest(error=type(error).__name__):
                writer = self.writer(error)
                with self.assertRaises(type(error)):
                    await close_http_writer(writer)
