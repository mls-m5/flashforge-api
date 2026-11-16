"""Direct wire-boundary checks; in-memory streams/writers, no network targets."""

import asyncio
import json
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from finderlab.web import WebError as PublicWebError
from finderlab.web_http import (
    HEADER_LIMIT, JSON_LIMIT, SLICE_JSON_LIMIT, WebError,
    post_content_length, read_json_body, read_request,
    write_head, write_problem, write_reply,
)


class MemoryWriter:
    def __init__(self):
        self.data = bytearray()
        self.drain = AsyncMock()
        self.transport = SimpleNamespace(abort=unittest.mock.Mock())

    def write(self, data):
        self.data.extend(data)


def reader_for(data, *, limit=HEADER_LIMIT, eof=True):
    reader = asyncio.StreamReader(limit=limit)
    reader.feed_data(data)
    if eof:
        reader.feed_eof()
    return reader


def expected_head(status, kind, length, extra=""):
    # Independent literal of the existing wire contract, including header order.
    return (
        f"HTTP/1.1 {status} Response\r\n"
        f"Content-Type: {kind}\r\nContent-Length: {length}\r\n"
        "Connection: close\r\nCache-Control: no-store\r\n"
        "X-Content-Type-Options: nosniff\r\nReferrer-Policy: no-referrer\r\n"
        "Content-Security-Policy: default-src 'none'; script-src 'self'; worker-src 'self'; "
        "style-src 'self'; img-src 'self'; connect-src 'self'; base-uri 'none'; "
        "frame-ancestors 'none'; form-action 'none'\r\n"
        + extra + "\r\n"
    ).encode("ascii")


class RequestTests(unittest.IsolatedAsyncioTestCase):
    async def test_split_crlf_preserves_target_headers_and_unread_body(self):
        entered = asyncio.Event()

        class ObservedReader(asyncio.StreamReader):
            async def readuntil(self, separator):
                entered.set()
                return await super().readuntil(separator)

        reader = ObservedReader(limit=HEADER_LIMIT)
        reader.feed_data(b"POST /api/file?name=a.stl HTTP/1.1\r\nHost: 127.0.0.1:8000\r\nX-Test: a:b\r\n\r")
        task = asyncio.create_task(read_request(reader))
        try:
            await asyncio.wait_for(entered.wait(), 1)
            self.assertFalse(task.done())
            reader.feed_data(b"\nbody")
            request = await asyncio.wait_for(task, 1)
            self.assertEqual(request.method, "POST")
            self.assertEqual(request.target, "/api/file?name=a.stl")
            self.assertEqual(request.headers, {"host": "127.0.0.1:8000", "x-test": "a:b"})
            self.assertEqual(await reader.readexactly(4), b"body")
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    async def test_header_names_are_case_folded_values_trimmed_and_duplicates_rejected(self):
        request = await read_request(reader_for(b"GET / HTTP/1.1\r\nHOST:  server  \r\n\r\n"))
        self.assertEqual(request.headers, {"host": "server"})
        for header in (b"Host: a\r\nhost: b", b" Host: a", b"Host : a", b": a"):
            with self.subTest(header=header), self.assertRaisesRegex(WebError, "Duplicate/invalid HTTP header"):
                await read_request(reader_for(b"GET / HTTP/1.1\r\n" + header + b"\r\n\r\n"))

    async def test_malformed_request_lines_headers_and_nonascii_propagate_for_server_mapping(self):
        for raw in (
            b"GET /\r\n\r\n", b"GET  / HTTP/1.1\r\n\r\n",
            b"GET / HTTP/1.1\r\nmissing-colon\r\n\r\n", b"GET / HTTP/1.1\r\nX: \xff\r\n\r\n",
        ):
            with self.subTest(raw=raw), self.assertRaises((ValueError, UnicodeError)):
                await read_request(reader_for(raw))
        with self.assertRaisesRegex(WebError, "Expected bounded HTTP/1.1 headers") as error:
            await read_request(reader_for(b"GET / HTTP/1.0\r\n\r\n"))
        self.assertEqual(error.exception.status, 400)

    async def test_exact_header_limit_and_both_oversize_paths(self):
        prefix = b"GET / HTTP/1.1\r\nX: "
        raw = prefix + b"a" * (HEADER_LIMIT - len(prefix) - 4) + b"\r\n\r\n"
        self.assertEqual(len(raw), HEADER_LIMIT)
        await read_request(reader_for(raw))
        with self.assertRaisesRegex(WebError, "Expected bounded HTTP/1.1 headers"):
            await read_request(reader_for(raw[:-4] + b"a\r\n\r\n"))
        with self.assertRaises(asyncio.LimitOverrunError):
            await read_request(reader_for(b"x" * (HEADER_LIMIT + 4)))

    async def test_incomplete_headers_are_not_a_partial_request(self):
        with self.assertRaises(asyncio.IncompleteReadError):
            await read_request(reader_for(b"GET / HTTP/1.1\r\nHost: localhost\r\n"))

    async def test_header_deadline_is_ten_seconds_and_timeout_propagates(self):
        reader = SimpleNamespace(readuntil=AsyncMock(side_effect=TimeoutError))
        original = asyncio.timeout
        with patch("finderlab.web_http.asyncio.timeout", wraps=original) as timeout:
            with self.assertRaises(TimeoutError):
                await read_request(reader)
        timeout.assert_called_once_with(10)

    async def test_parser_does_not_move_method_url_or_access_decisions_before_authentication(self):
        # Even malformed/unsupported targets/methods are checked after Basic auth
        # by WebServer, not by this syntax-only header read.
        for method, target in (("OPTIONS", "/api/state"), ("GET", "http://example.invalid/"), ("GET", "/#fragment")):
            with self.subTest(method=method, target=target):
                request = await read_request(reader_for(f"{method} {target} HTTP/1.1\r\n\r\n".encode()))
                self.assertEqual((request.method, request.target), (method, target))

    async def test_json_object_length_and_limits_leave_surplus_unread(self):
        for limit in (JSON_LIMIT, SLICE_JSON_LIMIT):
            data = b'{"value":"' + b"a" * (limit - 12) + b'"}'
            self.assertEqual(len(data), limit)
            reader = reader_for(data + b"surplus")
            self.assertEqual((await read_json_body(reader, limit, limit=limit))["value"], "a" * (limit - 12))
            self.assertEqual(await reader.read(), b"surplus")
        reader = SimpleNamespace(readexactly=AsyncMock())
        with self.assertRaisesRegex(WebError, "JSON body is too large") as error:
            await read_json_body(reader, JSON_LIMIT + 1)
        self.assertEqual(error.exception.status, 413)
        reader.readexactly.assert_not_called()

    async def test_invalid_incomplete_and_nonobject_json_retain_their_errors(self):
        for data in (b"[]", b"null", b"true", b"1", b'"text"'):
            with self.subTest(data=data), self.assertRaisesRegex(WebError, "Expected a JSON object"):
                await read_json_body(reader_for(data), len(data))
        with self.assertRaises(json.JSONDecodeError):
            await read_json_body(reader_for(b"{"), 1)
        with self.assertRaises(asyncio.IncompleteReadError):
            await read_json_body(reader_for(b"{"), 2)

    async def test_json_deadline_is_ten_seconds_and_timeout_propagates(self):
        reader = SimpleNamespace(readexactly=AsyncMock(side_effect=TimeoutError))
        original = asyncio.timeout
        with patch("finderlab.web_http.asyncio.timeout", wraps=original) as timeout:
            with self.assertRaises(TimeoutError):
                await read_json_body(reader, 2)
        timeout.assert_called_once_with(10)

    def test_post_length_is_strict_ascii_bounded_decimal_and_error_type_is_public(self):
        self.assertIs(PublicWebError, WebError)
        for raw in ("0", "0002", "9999999999"):
            self.assertEqual(post_content_length({"content-length": raw}), int(raw))
        for headers in ({}, *({"content-length": value} for value in ("", "-1", "+2", "2.0", "２", "1" * 11))):
            with self.subTest(headers=headers), self.assertRaises(WebError) as error:
                post_content_length(headers)
            self.assertEqual(error.exception.status, 411)
            self.assertEqual(str(error.exception), "A valid Content-Length is required")


class ResponseTests(unittest.IsolatedAsyncioTestCase):
    async def test_exact_json_response_bytes_and_security_headers(self):
        writer = MemoryWriter()
        await write_reply(writer, 200, {"name": "Räcke", "ok": True})
        body = b'{"name": "R\\u00e4cke", "ok": true}'
        self.assertEqual(writer.data, expected_head(200, "application/json", len(body)) + body)
        self.assertEqual(writer.drain.await_count, 2)

    async def test_binary_response_and_stream_head_preserve_extra_headers(self):
        writer = MemoryWriter()
        body = b"\x00\xff\r\n"
        await write_reply(writer, 200, body, "image/bmp", extra='ETag: "hash"\r\n')
        self.assertEqual(writer.data, expected_head(200, "image/bmp", len(body), 'ETag: "hash"\r\n') + body)
        writer = MemoryWriter()
        await write_head(writer, 200, "application/octet-stream", 123, 'ETag: "source"\r\n')
        self.assertEqual(writer.data, expected_head(200, "application/octet-stream", 123, 'ETag: "source"\r\n'))
        writer.drain.assert_awaited_once()

    async def test_basic_challenge_bytes_are_preserved(self):
        writer = MemoryWriter()
        challenge = 'WWW-Authenticate: Basic realm="Finder workbench", charset="UTF-8"\r\n'
        await write_reply(writer, 401, {"error": "LAN password required"}, extra=challenge)
        body = b'{"error": "LAN password required"}'
        self.assertEqual(writer.data, expected_head(401, "application/json", len(body), challenge) + body)

    async def test_head_and_body_writes_have_separate_ten_second_deadlines(self):
        writer = MemoryWriter()
        original = asyncio.wait_for
        with patch("finderlab.web_http.asyncio.wait_for", wraps=original) as wait:
            await write_reply(writer, 200, b"body")
        self.assertEqual([call.args[1] for call in wait.call_args_list], [10, 10])

    async def test_problem_aborts_on_io_or_timeout_without_retry(self):
        for error in (OSError("disconnected"), TimeoutError()):
            with self.subTest(error=type(error).__name__):
                writer = MemoryWriter()
                writer.drain.side_effect = error
                await write_problem(writer, 500, "Local I/O failed")
                writer.drain.assert_awaited_once()
                writer.transport.abort.assert_called_once()

    async def test_successful_problem_is_a_json_response_without_transport_close(self):
        writer = MemoryWriter()
        await write_problem(writer, 400, "Malformed or incomplete HTTP request")
        body = b'{"error": "Malformed or incomplete HTTP request"}'
        self.assertEqual(writer.data, expected_head(400, "application/json", len(body)) + body)
        writer.transport.abort.assert_not_called()

    async def test_cancellation_propagates_without_problem_retry(self):
        writer = MemoryWriter()
        writer.drain.side_effect = asyncio.CancelledError
        with self.assertRaises(asyncio.CancelledError):
            await write_problem(writer, 500, "cancelled")
        writer.drain.assert_awaited_once()
        writer.transport.abort.assert_not_called()
