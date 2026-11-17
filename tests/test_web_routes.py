"""Per-request route contracts with memory writers and project-local fake files."""

import asyncio
from dataclasses import replace
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch
from urllib.parse import urlsplit

from finderlab.web import WebConfig
from finderlab.web_http import WebError, write_head, write_reply
from finderlab.web_routes import STATIC_FILES, WebRoutes
from helpers import workspace_tempdir


class Writer:
    def __init__(self):
        self.chunks = []
        self.drain = AsyncMock()

    def write(self, data):
        self.chunks.append(data)

    @property
    def data(self):
        return b"".join(self.chunks)


class RouteTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = workspace_tempdir()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / "source.stl"
        self.payload = bytes(range(256)) * 600
        self.path.write_bytes(self.payload)
        self.state = {
            "models": [{"id": "part", "sha256": "source-hash"}],
            "source_sha256": "source-hash", "sha256": "print-hash",
            "suggested_name": "part.gcode", "gx_generated": False,
        }
        self.work = SimpleNamespace(
            state=self.state, model_paths={"part": self.path}, artifact=self.path,
            idle=Mock(), model_geometry=AsyncMock(return_value=(self.path, 2)),
            start=Mock(), discard=Mock(), remove_model=Mock(), receive=AsyncMock(),
            manual_action=Mock(return_value={"virtual_only": True}),
            manual_snapshot=Mock(return_value={"enabled": False}),
            manual_controls=None, toggle_monitor=Mock(), monitor=None,
        )
        self.routes = WebRoutes(
            work=self.work, config=WebConfig(), token="token", owned_dummy=False,
            head=write_head, reply=write_reply,
        )
        self.writer = Writer()

    async def post(self, path, data):
        body = json.dumps(data).encode()
        reader = asyncio.StreamReader()
        reader.feed_data(body)
        reader.feed_eof()
        await self.routes.post(
            reader, self.writer, urlsplit(path), {"content-type": "application/json"}, len(body),
        )

    async def test_post_operations_are_delegated_once_without_implementing_job_policy_in_routes(self):
        for operation in ("slice", "save", "start", "stop", "gx"):
            with self.subTest(operation=operation):
                data = {"confirm": True, "identity": "owned by workbench"}
                await self.post("/api/" + operation, data)
                self.work.start.assert_called_once_with(operation, data)
                self.work.start.reset_mock()
        await self.post("/api/discard", {"confirm": True})
        self.work.discard.assert_called_once_with()
        await self.post("/api/model-remove", {"confirm": True, "model_id": "part"})
        self.work.remove_model.assert_called_once_with({"confirm": True, "model_id": "part"})

    async def test_unknown_post_keeps_query_type_json_and_confirmation_error_order(self):
        for path, kind, body, status in (
            ("/missing?x=1", "text/plain", b"{", 400),
            ("/missing", "text/plain", b"{", 415),
            ("/missing", "application/json", b"[]", 400),
            ("/missing", "application/json", b"{}", 404),
            ("/api/discard", "application/json", b'{"confirm":false}', 404),
        ):
            with self.subTest(path=path, body=body):
                reader = asyncio.StreamReader()
                reader.feed_data(body)
                reader.feed_eof()
                with self.assertRaises(WebError) as error:
                    await self.routes.post(reader, self.writer, urlsplit(path), {"content-type": kind}, len(body))
                self.assertEqual(error.exception.status, status)
        self.work.start.assert_not_called()
        self.work.discard.assert_not_called()
        self.assertEqual(self.writer.data, b"")

    async def test_raw_receipt_preserves_exact_reader_length_and_decoded_name(self):
        reader = asyncio.StreamReader()
        await self.routes.post(
            reader, self.writer, urlsplit("/api/file?name=two%20parts.stl"),
            {"content-type": "application/octet-stream"}, 123,
        )
        self.work.receive.assert_awaited_once_with(reader, 123, "two parts.stl")
        self.work.start.assert_not_called()

    async def test_model_token_precedes_idle_query_and_geometry_then_identity_precedes_stream(self):
        self.work.idle.side_effect = WebError(409, "busy")
        with self.assertRaises(WebError) as error:
            await self.routes.get(self.writer, urlsplit("/api/model?invalid=1"), {})
        self.assertEqual(error.exception.status, 403)
        self.work.idle.assert_not_called()
        self.work.idle.side_effect = None
        with self.assertRaises(WebError) as error:
            await self.routes.get(self.writer, urlsplit("/api/model"), {
                "x-finder-token": "token", "if-match": '"old"',
            })
        self.assertEqual(error.exception.status, 412)
        self.work.model_geometry.assert_not_awaited()
        self.assertEqual(self.writer.data, b"")

    async def test_selected_model_stream_uses_its_hash_and_never_falls_back_to_first(self):
        await self.routes.get(self.writer, urlsplit("/api/model?model=part"), {
            "x-finder-token": "token", "if-match": '"source-hash"',
        })
        head, body = self.writer.data.split(b"\r\n\r\n", 1)
        self.assertEqual(body, self.payload)
        self.assertIn(b'ETag: "source-hash"\r\nX-Skipped-Facets: 0', head)
        self.work.model_geometry.assert_not_awaited()
        with self.assertRaises(WebError) as error:
            await self.routes.get(Writer(), urlsplit("/api/model?model=missing"), {"x-finder-token": "token"})
        self.assertEqual(error.exception.status, 404)
        self.work.model_geometry.assert_not_awaited()

    async def test_artifact_stream_preserves_deadline_headers_chunk_size_and_backpressure(self):
        original = asyncio.timeout
        with patch("finderlab.web_routes.asyncio.timeout", wraps=original) as timeout:
            await self.routes.get(self.writer, urlsplit("/api/artifact"), {"if-match": '"print-hash"'})
        timeout.assert_called_once_with(30)
        head, body = self.writer.data.split(b"\r\n\r\n", 1)
        self.assertEqual(body, self.payload)
        self.assertIn(b'Content-Disposition: attachment; filename="part.gcode"\r\nETag: "print-hash"', head)
        self.assertEqual([len(data) for data in self.writer.chunks[1:]], [65536, 65536, len(self.payload) - 131072])
        self.assertEqual(self.writer.drain.await_count, len(self.writer.chunks))
        self.assertEqual(self.path.read_bytes(), self.payload)

    async def test_stream_error_or_cancellation_propagates_without_delete_or_retry(self):
        for error in (OSError("disconnected"), asyncio.CancelledError()):
            with self.subTest(error=type(error).__name__):
                writer = Writer()
                writer.drain.side_effect = [None, error]
                with self.assertRaises(type(error)):
                    await self.routes.get(writer, urlsplit("/api/artifact"), {})
                self.assertEqual(writer.drain.await_count, 2)
                self.assertEqual(self.path.read_bytes(), self.payload)

    async def test_thumbnail_checks_busy_and_hash_before_reading_exact_embedded_bitmap(self):
        self.work.idle.side_effect = WebError(409, "busy")
        with self.assertRaises(WebError) as error:
            await self.routes.get(self.writer, urlsplit("/api/gx-thumbnail?v=old"), {})
        self.assertEqual(error.exception.status, 409)
        self.work.idle.side_effect = None
        self.state["gx_generated"] = True
        with self.assertRaises(WebError) as error:
            await self.routes.get(self.writer, urlsplit("/api/gx-thumbnail?v=old"), {})
        self.assertEqual(error.exception.status, 412)
        gx = bytearray(14512)
        gx[:12] = b"xgcode 1.0\n\0"
        gx[58:60] = b"BM"
        self.path.write_bytes(gx)
        await self.routes.get(self.writer, urlsplit("/api/gx-thumbnail?v=print-hash"), {})
        head, body = self.writer.data.split(b"\r\n\r\n", 1)
        self.assertIn(b"Content-Type: image/bmp", head)
        self.assertEqual(body, bytes(gx[58:]))
        self.path.write_bytes(b"invalid")
        with self.assertRaises(WebError) as error:
            await self.routes.get(Writer(), urlsplit("/api/gx-thumbnail?v=print-hash"), {})
        self.assertEqual(error.exception.status, 422)

    async def test_config_and_cached_gets_use_current_dependencies_without_changing_state(self):
        self.routes.config = replace(self.routes.config, enable_upload=True)
        self.routes.owned_dummy = True
        before = dict(self.state)
        await self.routes.get(self.writer, urlsplit("/api/config"), {})
        body = json.loads(self.writer.data.split(b"\r\n\r\n", 1)[1])
        self.assertTrue(body["upload_enabled"])
        self.assertTrue(body["owned_dummy"])
        self.assertEqual(body["token"], "token")
        await self.routes.get(Writer(), urlsplit("/api/state"), {})
        await self.routes.get(Writer(), urlsplit("/api/manual-state"), {})
        self.assertEqual(self.state, before)
        self.work.start.assert_not_called()
        self.work.idle.assert_not_called()

    def test_static_allowlist_public_reexports_and_shared_limits_remain_compatible(self):
        from finderlab import web, web_limits
        self.assertIs(web.STATIC_FILES, STATIC_FILES)
        self.assertEqual(web.MODEL_LIMIT, web_limits.MODEL_LIMIT)
        self.assertEqual(web.PRINT_LIMIT, web_limits.PRINT_LIMIT)
        self.assertEqual(STATIC_FILES["/vendor/three/LICENSE"], ("vendor/three/LICENSE", "text/plain; charset=utf-8"))
        self.assertNotIn("/../web.py", STATIC_FILES)
