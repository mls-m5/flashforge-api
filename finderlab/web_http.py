"""The workbench's narrow HTTP/1.1 wire boundary, not a general HTTP server.

This module owns bounded header/JSON reads and response bytes only. Peer/Host /
Basic/Origin/token checks, route selection, connection/task lifetime and file
streaming remain with WebServer. It never imports the workbench or printer client.
Malformed/incomplete reads propagate to the server's existing error mapping.
"""

import asyncio
from dataclasses import dataclass
import json

HEADER_LIMIT = 16384
REQUEST_TIMEOUT = 10
RESPONSE_TIMEOUT = 10
JSON_LIMIT = 2048
SLICE_JSON_LIMIT = 8192


class WebError(ValueError):
    """An explicit HTTP rejection, shared with workbench policy validation."""

    def __init__(self, status, message):
        self.status = status
        super().__init__(message)


@dataclass(frozen=True)
class Request:
    """Header data only; URL/body interpretation follows the common access gates."""

    method: str
    target: str
    headers: dict[str, str]


async def read_request(reader):
    """Read exactly one bounded header section, leaving body/surplus untouched.

    The server must also configure StreamReader's limit to HEADER_LIMIT. Keep
    the post-read size check: the stream delimiter limit and total header size
    are not identical. Do not normalize paths, collapse headers or accept new
    HTTP syntax as a side effect of this extraction.
    """
    async with asyncio.timeout(REQUEST_TIMEOUT):
        raw = await reader.readuntil(b"\r\n\r\n")
    lines = raw.decode("ascii").split("\r\n")
    method, target, version = lines[0].split(" ")
    if version != "HTTP/1.1" or len(raw) > HEADER_LIMIT:
        raise WebError(400, "Expected bounded HTTP/1.1 headers")

    headers = {}
    for line in lines[1:-2]:
        key, value = line.split(":", 1)
        key = key.lower()
        if not key or key in headers or key.strip() != key:
            raise WebError(400, "Duplicate/invalid HTTP header")
        headers[key] = value.strip()
    return Request(method, target, headers)


def post_content_length(headers):
    """Called only after POST access checks; GET retains its separate body rule."""
    length_text = headers.get("content-length", "")
    if not length_text.isascii() or not length_text.isdecimal() or len(length_text) > 10:
        raise WebError(411, "A valid Content-Length is required")
    return int(length_text)


async def read_json_body(reader, length, *, limit=JSON_LIMIT):
    """Read the declared JSON object only, after route/type/access validation."""
    if length > limit:
        raise WebError(413, "JSON body is too large")
    async with asyncio.timeout(REQUEST_TIMEOUT):
        data = json.loads(await reader.readexactly(length))
    if not isinstance(data, dict):
        raise WebError(400, "Expected a JSON object")
    return data


async def write_head(writer, status, kind, length, extra=""):
    writer.write((
        f"HTTP/1.1 {status} Response\r\nContent-Type: {kind}\r\nContent-Length: {length}\r\n"
        "Connection: close\r\nCache-Control: no-store\r\nX-Content-Type-Options: nosniff\r\n"
        "Referrer-Policy: no-referrer\r\n"
        "Content-Security-Policy: default-src 'none'; script-src 'self'; worker-src 'self'; "
        "style-src 'self'; img-src 'self'; connect-src 'self'; base-uri 'none'; "
        "frame-ancestors 'none'; form-action 'none'\r\n"
        + extra + "\r\n"
    ).encode("ascii"))
    await asyncio.wait_for(writer.drain(), RESPONSE_TIMEOUT)


async def write_reply(writer, status, data, kind="application/json", *, extra=""):
    if not isinstance(data, bytes):
        data = json.dumps(data, ensure_ascii=True).encode()
    await write_head(writer, status, kind, len(data), extra)
    writer.write(data)
    await asyncio.wait_for(writer.drain(), RESPONSE_TIMEOUT)


async def write_problem(writer, status, message):
    """A disconnected/blocked writer must not cause a retry or escape cleanup."""
    try:
        await write_reply(writer, status, {"error": message})
    except (OSError, TimeoutError):
        writer.transport.abort()
