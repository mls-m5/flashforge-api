"""HTTP extraction keeps access/error ordering and connection lifecycle intact."""

import asyncio
from dataclasses import replace
import json
from unittest.mock import patch

from finderlab.web import WebServer
from web_helpers import WebTestCase, close_http_writer


class WebHttpIntegrationTests(WebTestCase):
    async def raw_request(self, request):
        reader, writer = await asyncio.open_connection(*self.server.address)
        try:
            writer.write(request)
            await writer.drain()
            writer.write_eof()
            data = await asyncio.wait_for(reader.read(), 4)
        finally:
            await close_http_writer(writer)
        head, body = data.split(b"\r\n\r\n", 1)
        self.assertIn(b"Connection: close\r\n", head)
        self.assertIn(b"Content-Security-Policy:", head)
        return int(head.split(b" ")[1]), json.loads(body)

    async def test_raw_malformed_duplicate_incomplete_and_oversized_headers_map_to_400(self):
        authority = self.server.authority.encode()
        requests = (
            b"GET / HTTP/1.0\r\n\r\n",
            b"GET / HTTP/1.1\r\nHost: " + authority + b"\r\nhost: duplicate\r\n\r\n",
            b"GET / HTTP/1.1\r\nHost: " + authority + b"\r\ninvalid-header\r\n\r\n",
            b"GET / HTTP/1.1\r\nHost: " + authority + b"\r\n",
            b"GET / HTTP/1.1\r\nX: \xff\r\n\r\n",
            b"GET / HTTP/1.1\r\nX: " + b"a" * 16384 + b"\r\n\r\n",
        )
        with patch("finderlab.web.FinderClient") as client:
            for request in requests:
                with self.subTest(prefix=request[:80]):
                    code, body = await self.raw_request(request)
                    self.assertEqual(code, 400, body)
            client.assert_not_called()
        self.assertEqual(self.server.work.state["phase"], "empty")
        self.assertEqual(list(self.server.work.folder.glob("captures/*")), [])

    async def test_common_access_and_validation_order_precedes_body_and_route_side_effects(self):
        await self.server.__aexit__(None, None, None)
        self.server = await WebServer(replace(self.config, lan=True)).__aenter__()
        base = {"Host": self.server.authority}
        malformed = {"Transfer-Encoding": "chunked", "Content-Length": "invalid"}
        with patch("finderlab.web.FinderClient") as client:
            # Host check precedes authentication; auth precedes transfer/method/URL.
            code, _ = await self.request("OPTIONS", "http://example.invalid/", headers={**malformed, "Host": "wrong"})
            self.assertEqual(code, 403)
            code, _ = await self.request("OPTIONS", "http://example.invalid/", headers={**base, **malformed})
            self.assertEqual(code, 401)
            self.assertIn(b'WWW-Authenticate: Basic realm="Finder workbench"', self.last_headers)
            # A denied peer is rejected even before header parsing.
            with patch.object(self.server.access, "allows_peer", return_value=False):
                code, _ = await self.raw_request(b"not even HTTP\r\n\r\n")
                self.assertEqual(code, 403)
            client.assert_not_called()
        self.assertEqual(self.server.work.state["phase"], "empty")

    async def test_authenticated_transport_method_and_origin_checks_keep_existing_order(self):
        with patch("finderlab.web.FinderClient") as client:
            code, _ = await self.request("OPTIONS", "/", headers={"Expect": "100-continue"})
            self.assertEqual(code, 400, "unsupported transfer is checked before method")
            code, _ = await self.request("OPTIONS", "http://example.invalid/")
            self.assertEqual(code, 405, "method is checked before URL")
            code, _ = await self.request("POST", "/api/save", headers={"Origin": "http://wrong", "Content-Length": "invalid"})
            self.assertEqual(code, 403, "origin is checked before length")
            code, _ = await self.request("POST", "/api/save", headers={"Content-Length": "invalid"})
            self.assertEqual(code, 411)
            for header in ("Transfer-Encoding", "Expect"):
                code, body = await self.request("GET", "/api/state", headers={header: "unsupported"})
                self.assertEqual(code, 400)
                self.assertIn(b"Chunked/Expect requests are not supported", body)
            client.assert_not_called()

    async def test_json_limits_and_incomplete_body_map_before_workbench_operations(self):
        with patch("finderlab.web.FinderClient") as client:
            for path, limit in (("/api/save", 2048), ("/api/slice", 8192)):
                with self.subTest(path=path):
                    # Valid object at the exact limit reaches the workbench's
                    # documented-fields rejection; one extra byte never does.
                    body = b'{"padding":"' + b"a" * (limit - 14) + b'"}'
                    self.assertEqual(len(body), limit)
                    code, response = await self.request("POST", path, body)
                    self.assertEqual(code, 400)
                    self.assertIn(b"Explicit confirmation", response)
                    code, response = await self.request("POST", path, body + b" ")
                    self.assertEqual(code, 413)
                    self.assertIn(b"JSON body is too large", response)
            code, _ = await self.request(
                "POST", "/api/discard", b"{", {"Content-Length": "2"}, early_eof=True,
            )
            self.assertEqual(code, 400)
            code, response = await self.post("/api/discard", [])
            self.assertEqual(code, 400)
            self.assertIn(b"Expected a JSON object", response)
            client.assert_not_called()
        self.assertIsNone(self.server.work.task)
        self.assertEqual(list(self.server.work.folder.glob("captures/*")), [])
