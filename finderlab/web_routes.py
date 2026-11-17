"""Workbench routes after WebServer's common access checks.

A per-request adapter: no listener, authentication bypass, printer session or
independent copy of mutable workbench state. WebServer owns the common gates,
error mapping and connection/task lifetime. Workbench still owns all mutations,
operation admission, identity/state and source/cache/storage lifetimes.
"""

import asyncio
from pathlib import Path
import secrets
from urllib.parse import parse_qs

from .passive_status import status_from_capture
from .web_http import SLICE_JSON_LIMIT, WebError, read_json_body
from .web_limits import MODEL_LIMIT, PRINT_LIMIT

STATIC = Path(__file__).with_name("webstatic")
STATIC_FILES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/style.css": ("style.css", "text/css; charset=utf-8"),
}
for _name in (
    "app.js", "manual.js", "preview.js", "toolpath-view.js", "toolpath-worker.js",
    "model-preview.js", "model-worker.js", "model-transform.js", "plate-preview.js",
    "vendor/three/three.module.min.js", "vendor/three/OrbitControls.js",
):
    STATIC_FILES["/" + _name] = (_name, "text/javascript; charset=utf-8")
STATIC_FILES["/vendor/three/LICENSE"] = ("vendor/three/LICENSE", "text/plain; charset=utf-8")


class WebRoutes:
    """Explicit route dependencies, not a registry or a proxy for WebServer.

    head/reply are the server's response entry points. The config/workbench
    references are bound per request, not cached across configuration changes.
    Call post/get only after the server's common method/URL/access checks.
    """

    def __init__(self, *, work, config, token, owned_dummy, head, reply):
        self.work = work
        self.config = config
        self.token = token
        self.owned_dummy = owned_dummy
        self.head = head
        self.reply = reply

    async def post(self, reader, writer, uri, headers, length):
        if uri.path == "/api/file":
            if headers.get("content-type") != "application/octet-stream":
                raise WebError(415, "Expected raw file bytes")
            query = parse_qs(uri.query, strict_parsing=True, max_num_fields=1)
            if set(query) != {"name"} or len(query["name"]) != 1:
                raise WebError(400, "A single filename is required")
            await self.work.receive(reader, length, query["name"][0])
        else:
            if uri.query:
                raise WebError(400, "Unexpected query")
            if headers.get("content-type") != "application/json":
                raise WebError(415, "Expected JSON")
            if uri.path == "/api/slice":
                data = await read_json_body(reader, length, limit=SLICE_JSON_LIMIT)
            else:
                data = await read_json_body(reader, length)
            if uri.path == "/api/manual":
                await self.reply(writer, 200, self.work.manual_action(data))
                return
            if uri.path == "/api/monitor":
                self.work.toggle_monitor(data)
                report = self.work.monitor.report() if self.work.monitor else {"monitor_running": False}
                await self.reply(writer, 200, report)
                return
            if uri.path == "/api/model-remove":
                self.work.remove_model(data)
            elif uri.path == "/api/discard" and set(data) == {"confirm"} and data["confirm"] is True:
                self.work.discard()
            elif uri.path in ("/api/slice", "/api/save", "/api/start", "/api/stop", "/api/gx"):
                self.work.start(uri.path.removeprefix("/api/"), data)
            else:
                raise WebError(404, "Unknown operation")
        await self.reply(writer, 200, self.work.state)

    async def get(self, writer, uri, headers):
        if (
            (uri.query and uri.path not in ("/api/gx-thumbnail", "/api/model"))
            or int(headers.get("content-length", "0")) != 0
        ):
            raise WebError(400, "Unexpected query/body")
        if uri.path == "/api/config":
            await self.reply(writer, 200, self.configuration())
        elif uri.path == "/api/printer-status":
            report = self.work.monitor.report() if self.work.monitor else status_from_capture(
                self.config.status_capture, self.config.client.host, self.config.client.port,
            )
            await self.reply(writer, 200, report)
        elif uri.path == "/api/manual-state":
            await self.reply(writer, 200, self.work.manual_snapshot())
        elif uri.path == "/api/state":
            await self.reply(writer, 200, self.work.state)
        elif uri.path == "/api/model":
            await self.model(writer, uri, headers)
        elif uri.path == "/api/gx-thumbnail":
            await self.thumbnail(writer, uri)
        elif uri.path == "/api/artifact":
            await self.artifact(writer, headers)
        elif uri.path in STATIC_FILES:
            name, kind = STATIC_FILES[uri.path]
            await self.reply(writer, 200, (STATIC / name).read_bytes(), kind)
        else:
            raise WebError(404, "Not found")

    def configuration(self):
        """The unchanged public config snapshot; never expose paths/credentials."""
        return {
            "token": self.token,
            "target": f"{self.config.client.host}:{self.config.client.port}",
            "upload_enabled": self.config.enable_upload,
            "job_controls_enabled": self.config.enable_job_controls,
            "slicing_enabled": self.config.slicing is not None,
            "priming_review_enabled": bool(self.config.slicing and self.config.slicing.check_priming),
            "sliced_upload_enabled": self.config.allow_sliced_upload,
            "print_limit": PRINT_LIMIT,
            "model_limit": MODEL_LIMIT,
            "storage_limit": self.config.storage_limit,
            "auto_archive": self.config.auto_archive,
            "passive_status_enabled": self.config.status_capture is not None,
            "active_monitor_enabled": self.config.enable_monitor,
            "auto_monitor": self.config.auto_monitor,
            "manual_virtual_enabled": self.work.manual_controls is not None,
            "lan_mode": self.config.lan,
            "owned_dummy": self.owned_dummy,
        }

    async def model(self, writer, uri, headers):
        # This read may prepare a bounded private 3MF derivative: keep its token
        # gate before busy/query/identity checks and any geometry/cache work.
        if not secrets.compare_digest(headers.get("x-finder-token", ""), self.token):
            raise WebError(403, "Reload the page before requesting model preview")
        self.work.idle()
        chosen = None
        if uri.query:
            query = parse_qs(uri.query, strict_parsing=True, max_num_fields=1)
            if set(query) != {"model"} or len(query["model"]) != 1:
                raise WebError(400, "Expected one model id")
            chosen = next((model for model in self.work.state["models"] if model["id"] == query["model"][0]), None)
            if not chosen:
                raise WebError(404, "No such model")
        tag = '"' + (chosen["sha256"] if chosen else self.work.state["source_sha256"]) + '"'
        if "if-match" in headers and headers["if-match"] != tag:
            raise WebError(412, "Source model changed; reload model preview")
        if chosen and self.work.model_paths[chosen["id"]].suffix == ".stl":
            path, skipped = self.work.model_paths[chosen["id"]], 0
        else:
            path, skipped = await self.work.model_geometry()
        await self.stream_file(writer, path, 'ETag: ' + tag + '\r\nX-Skipped-Facets: ' + str(skipped) + '\r\n')

    async def thumbnail(self, writer, uri):
        self.work.idle()
        if not self.work.artifact or not self.work.state["gx_generated"]:
            raise WebError(404, "No generated GX thumbnail")
        if uri.query != "v=" + self.work.state["sha256"]:
            raise WebError(412, "GX identity changed; refresh before viewing thumbnail")
        with self.work.artifact.open("rb") as source:
            prefix = source.read(14512)
        if len(prefix) != 14512 or prefix[:12] != b"xgcode 1.0\n\0" or prefix[58:60] != b"BM":
            raise WebError(422, "Generated thumbnail is unavailable")
        await self.reply(writer, 200, prefix[58:14512], "image/bmp")

    async def artifact(self, writer, headers):
        self.work.idle()
        if not self.work.artifact:
            raise WebError(404, "No print-file artifact")
        etag = '"' + self.work.state["sha256"] + '"'
        if "if-match" in headers and headers["if-match"] != etag:
            raise WebError(412, "Artifact changed; refresh preview before loading")
        await self.stream_file(
            writer, self.work.artifact,
            'Content-Disposition: attachment; filename="' + self.work.state["suggested_name"]
            + '"\r\nETag: ' + etag + '\r\n',
        )

    async def stream_file(self, writer, path, extra):
        """Stream an already-selected file; caller owns access/identity checks.

        Preserve the open/stat/deadline order, 64KiB chunks and backpressure.
        This adapter never deletes/caches files or acquires a new storage lock.
        """
        with path.open("rb") as source:
            async with asyncio.timeout(30):
                await self.head(writer, 200, "application/octet-stream", path.stat().st_size, extra)
                while chunk := source.read(65536):
                    writer.write(chunk)
                    await writer.drain()
