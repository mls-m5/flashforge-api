"""Loopback-only, single-slot web workbench. No automatic printer connection.

Deliberately narrow HTTP/1.1 subset (Content-Length, close after one request).
Not a general purpose web server or an Internet-facing service.
"""

import asyncio
from dataclasses import dataclass, field
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import secrets
import shutil
import signal
from urllib.parse import parse_qs, urlsplit
import uuid

from .capture import Capture, CaptureError
from .client import ClientConfig, FinderClient, remote_path
from .slicer import SliceConfig, slice_model

STATIC = Path(__file__).with_name("webstatic")
PRINT_LIMIT = 8 * 1024 * 1024
MODEL_LIMIT = 64 * 1024 * 1024
CAPTURE_LIMIT = 64 * 1024 * 1024
STORAGE_LIMIT = 256 * 1024 * 1024


class WebError(ValueError):
    def __init__(self, status, message):
        self.status = status
        super().__init__(message)


class WebCapture(Capture):
    """Retain authoritative raw diagnostics; expose only a bounded UI excerpt."""
    def __init__(self, *args, state, **kwargs):
        self.state = state
        super().__init__(*args, **kwargs)

    def event(self, kind, session_id=None, **fields):
        result = super().event(kind, session_id, **fields)
        if kind == "slicer_output":
            self.state["slicer_log"] = (self.state["slicer_log"] + fields.get("text", ""))[-4000:]
        return result


@dataclass(frozen=True)
class WebConfig:
    host: str = "127.0.0.1"
    port: int = 8000
    data_dir: Path = Path("web-data")
    client: ClientConfig = field(default_factory=ClientConfig)
    enable_upload: bool = False
    enable_job_controls: bool = False
    slicing: SliceConfig | None = None
    allow_sliced_upload: bool = False

    def __post_init__(self):
        if os.name != "posix":
            raise ValueError("The experimental web workbench currently requires POSIX/Linux workspace locking")
        if not ipaddress.ip_address(self.host).is_loopback:
            raise ValueError("The experimental web server must bind to loopback")
        if not 0 <= self.port <= 65535:
            raise ValueError("Invalid web port")
        if self.client.max_file_size != PRINT_LIMIT:
            raise ValueError("Web print-file limit is fixed at 8 MiB")
        if self.slicing and (self.slicing.max_output_size > PRINT_LIMIT or self.slicing.max_model_size > MODEL_LIMIT):
            raise ValueError("Slicer limits exceed the web workbench limits")


class Workbench:
    """One resident file and one active operation; never queues or auto-saves."""
    def __init__(self, config):
        self.config = config
        self.folder = Path(config.data_dir).resolve()
        self.folder.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.source = None
        self.artifact = None
        self.slot = None
        self.task = None
        self.state = self.empty()
        # Do not let two servers operate the same workspace at once.
        import fcntl
        self.lock = (self.folder / "workbench.lock").open("a")
        try:
            fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BaseException:
            self.lock.close()
            raise

    @staticmethod
    def empty():
        return {"busy": False, "phase": "empty", "saved": False, "acknowledged": 0,
                "size": 0, "name": "", "error": "", "warning": "", "capture": "",
                "sha256": "", "sliced": False, "artifact": False, "slicer_log": "",
                "saved_name": "", "save_id": "", "start_attempted": False, "job_result": "not_requested"}

    def capacity(self, reserve):
        total = count = 0
        for path in self.folder.rglob("*"):
            count += 1
            if path.is_symlink() or not (path.is_file() or path.is_dir()):
                raise WebError(507, "Unexpected symlink/special file in web storage")
            if path.is_file():
                total += path.stat().st_size
            if count > 4096:
                raise WebError(507, "Web storage entry limit reached; archive private logs locally")
        if total + reserve > STORAGE_LIMIT:
            raise WebError(507, "Web storage quota reached; archive private logs locally before continuing")

    def idle(self):
        if self.state["busy"]:
            raise WebError(409, "An operation is active; there is no queue")

    async def receive(self, reader, length, name):
        self.idle()
        if self.source is not None:
            raise WebError(409, "Discard the current file before choosing another")
        if (not isinstance(name, str) or not 1 <= len(name) <= 200 or "/" in name or "\\" in name
                or any(ord(c) < 32 or ord(c) == 127 for c in name)):
            raise WebError(400, "Use a plain filename, not a path or control characters")
        suffix = Path(name).suffix.lower()
        if suffix not in (".stl", ".gx", ".gcode", ".g"):
            raise WebError(400, "Choose STL, GX, G-code or G")
        limit = MODEL_LIMIT if suffix == ".stl" else PRINT_LIMIT
        if not 0 < length <= limit:
            raise WebError(413, f"File must contain 1–{limit} bytes")
        self.capacity(length + 4096)
        self.state = {**self.empty(), "busy": True, "phase": "receiving", "name": name}
        self.slot = self.folder / ("file-" + uuid.uuid4().hex)
        path = self.slot / ("source" + suffix)
        digest = hashlib.sha256()
        try:
            self.slot.mkdir(mode=0o700)
            async with asyncio.timeout(60):
                with path.open("xb") as writer:
                    remaining = length
                    while remaining:
                        chunk = await reader.read(min(65536, remaining))
                        if not chunk:
                            raise WebError(400, "File body ended early")
                        writer.write(chunk)
                        digest.update(chunk)
                        remaining -= len(chunk)
            self.source = path
            self.artifact = path if suffix != ".stl" else None
            self.state.update(phase="model_ready" if suffix == ".stl" else "file_ready",
                              size=length, sha256=digest.hexdigest(), artifact=self.artifact is not None)
        except BaseException:
            shutil.rmtree(self.slot, ignore_errors=True)
            self.slot = None
            self.state = self.empty()
            raise
        finally:
            self.state["busy"] = False

    def discard(self):
        self.idle()
        if self.slot:
            shutil.rmtree(self.slot)
        self.source = self.artifact = self.slot = None
        self.state = self.empty()

    def start(self, operation, data):
        self.idle()
        if operation not in ("slice", "save", "start", "stop"):
            raise WebError(400, "Unknown operation")
        allowed = {"confirm", "remote_name"} if operation == "save" else {"confirm", "save_id"} if operation == "start" else {"confirm"}
        if set(data) - allowed or data.get("confirm") is not True:
            raise WebError(400, "Explicit confirmation and only documented fields are required")
        if operation in ("start", "stop"):
            if not self.config.enable_job_controls:
                raise WebError(409, "Job controls require server --enable-job-controls")
            if operation == "start":
                if not self.state["saved"] or not self.state["saved_name"] or self.state["phase"] == "unknown":
                    raise WebError(409, "Start requires an unambiguous confirmed save in this slot")
                if data.get("save_id") != self.state["save_id"]:
                    raise WebError(409, "Saved file changed; refresh before confirming Start")
                if self.state["start_attempted"]:
                    raise WebError(409, "Start was already attempted; do not blindly repeat it")
            self.capacity(CAPTURE_LIMIT + 1024 * 1024)
            if operation == "start":
                self.state["start_attempted"] = True
            self.state.update(busy=True, phase="connecting", error="", warning="", capture="")
            self.task = asyncio.create_task(self._operation(operation, data))
            return
        if self.source is None:
            raise WebError(409, "Choose a file first")
        if operation == "slice":
            if not self.config.slicing:
                raise WebError(409, "Orca is not configured; no validated Finder profile ships with this page")
            if self.source.suffix != ".stl" or self.artifact:
                raise WebError(409, "Slicing needs a new STL; discard before slicing another version")
        else:
            if not self.config.enable_upload:
                raise WebError(409, "Printer uploads are disabled on the server")
            if self.artifact is None:
                raise WebError(409, "Slice successfully and review the generated output before saving")
            if self.state["saved"]:
                raise WebError(409, "This file was already saved; no implicit repeat upload")
            if self.state["phase"] == "unknown":
                raise WebError(409, "Previous save is uncertain; inspect physical state/logs, then discard to reset")
            if self.state["sliced"] and not self.config.allow_sliced_upload:
                raise WebError(409, "Generated-output uploads need server --allow-sliced-upload after separate profile review")
            name = data.get("remote_name")
            if not isinstance(name, str):
                raise WebError(400, "An ASCII remote basename is required")
            try:
                remote_path(name)
            except ValueError as exc:
                raise WebError(400, str(exc)) from exc
            if self.state["sliced"] and Path(name).suffix.lower() not in (".gcode", ".g"):
                raise WebError(400, "Plain sliced G-code cannot be renamed to GX")
        self.capacity(CAPTURE_LIMIT + PRINT_LIMIT + 1024 * 1024)
        self.state.update(busy=True, phase="slicing" if operation == "slice" else "connecting", error="", warning="", capture="")
        if operation == "slice":
            self.state["slicer_log"] = ""
        self.task = asyncio.create_task(self._operation(operation, data))

    async def _operation(self, operation, data):
        capture = None
        network = False
        try:
            capture = WebCapture(self.folder / "captures", "slice" if operation == "slice" else "client", state=self.state,
                              max_bytes=CAPTURE_LIMIT, max_sessions=1,
                              metadata={"operation": operation, "start_requested": operation == "start", "interface": "standalone-web"})
            self.state["capture"] = str(capture.path)
            if operation == "start":
                capture.manifest["metadata"].update(saved_name=self.state["saved_name"], save_id=self.state["save_id"])
            if operation == "slice":
                result = await slice_model(self.source, self.slot / "sliced.gcode", self.config.slicing, capture=capture)
                self.artifact = result.path
                self.state.update(phase="review", sliced=True, artifact=True, size=result.size, sha256=result.sha256)
                capture.manifest["metadata"]["slicing_confirmed"] = True
            else:
                network = True
                async with asyncio.timeout(900):
                    async with FinderClient(self.config.client, capture=capture) as client:
                        capture.manifest.update(model="Flashforge Finder", firmware="V1.5 20170419")
                        if operation == "save":
                            self.state["phase"] = "uploading"
                            def progress(count, size):
                                self.state.update(acknowledged=count, size=size)
                            result = await client.upload(self.artifact, remote_name=data["remote_name"], progress=progress)
                            self.state.update(phase="saved", saved=True, sha256=result.sha256,
                                              saved_name=result.path.removeprefix("0:/user/"), save_id=uuid.uuid4().hex)
                            capture.manifest["metadata"].update(upload_confirmed=True, remote_path=result.path, save_id=self.state["save_id"])
                        elif operation == "start":
                            await client.start(self.state["saved_name"], confirm=True)
                            self.state.update(phase="start_acknowledged", job_result="start_acknowledged")
                            capture.manifest["metadata"]["start_acknowledged"] = True
                        else:
                            await client.stop(confirm=True)
                            self.state.update(phase="cancel_acknowledged", job_result="cancel_acknowledged")
                            capture.manifest["metadata"]["stop_acknowledged"] = True
                    if client.cleanup_error:
                        self.state["warning"] = "Operation confirmed, but release failed: " + client.cleanup_error
        except BaseException as exc:
            self.state.update(phase="unknown" if network else "failed", error=str(exc) or type(exc).__name__)
            if operation in ("start", "stop"):
                self.state["job_result"] = operation + "_unknown" if network else "not_sent"
            if capture and not capture.failed:
                try:
                    capture.event("error", phase=self.state["phase"], error_type=type(exc).__name__, message=str(exc))
                except OSError:
                    pass
            if isinstance(exc, asyncio.CancelledError):
                raise
        finally:
            try:
                if capture:
                    capture.close()
                    if capture.failed:
                        raise CaptureError("Recording is incomplete; do not retry blindly")
            except Exception as exc:
                self.state.update(phase="unknown" if network else "failed", error="Recording failed: " + str(exc))
            finally:
                self.state["busy"] = False

    async def close(self):
        if self.task and not self.task.done():
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
        self.lock.close()


class WebServer:
    def __init__(self, config):
        self.config = config
        self.work = None
        self.token = secrets.token_urlsafe(32)
        self.server = None
        self.clients = set()
        self.address = None

    async def __aenter__(self):
        self.work = Workbench(self.config)
        try:
            self.server = await asyncio.start_server(self.handle, self.config.host, self.config.port, limit=16384)
            self.address = self.server.sockets[0].getsockname()[:2]
            return self
        except BaseException:
            await self.work.close()
            raise

    async def __aexit__(self, *_):
        self.server.close()
        await self.server.wait_closed()
        for task in list(self.clients):
            task.cancel()
        await asyncio.gather(*self.clients, return_exceptions=True)
        await self.work.close()

    @property
    def authority(self):
        host, port = self.address
        return f"[{host}]:{port}" if ":" in host else f"{host}:{port}"

    async def handle(self, reader, writer):
        task = asyncio.current_task()
        if len(self.clients) >= 16:
            writer.close()
            return
        self.clients.add(task)
        try:
            async with asyncio.timeout(10):
                raw = await reader.readuntil(b"\r\n\r\n")
            lines = raw.decode("ascii").split("\r\n")
            method, target, version = lines[0].split(" ")
            if version != "HTTP/1.1" or len(raw) > 16384:
                raise WebError(400, "Expected bounded HTTP/1.1 headers")
            headers = {}
            for line in lines[1:-2]:
                key, value = line.split(":", 1)
                key = key.lower()
                if not key or key in headers or key.strip() != key:
                    raise WebError(400, "Duplicate/invalid HTTP header")
                headers[key] = value.strip()
            if headers.get("host") != self.authority:
                raise WebError(403, "Use the exact loopback URL printed by the server")
            if "transfer-encoding" in headers or "expect" in headers:
                raise WebError(400, "Chunked/Expect requests are not supported")
            if method not in ("GET", "POST"):
                raise WebError(405, "Only GET and POST are supported")
            uri = urlsplit(target)
            if uri.scheme or uri.netloc or uri.fragment:
                raise WebError(400, "Expected a relative URL")
            if method == "POST":
                if headers.get("origin") != "http://" + self.authority or not secrets.compare_digest(headers.get("x-finder-token", ""), self.token):
                    raise WebError(403, "Same-origin request and session token required; reload the page if the server restarted")
                length_text = headers.get("content-length", "")
                if not length_text.isascii() or not length_text.isdecimal() or len(length_text) > 10:
                    raise WebError(411, "A valid Content-Length is required")
                length = int(length_text)
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
                    if length > 2048:
                        raise WebError(413, "JSON body is too large")
                    async with asyncio.timeout(10):
                        data = json.loads(await reader.readexactly(length))
                    if not isinstance(data, dict):
                        raise WebError(400, "Expected a JSON object")
                    if uri.path == "/api/discard" and set(data) == {"confirm"} and data["confirm"] is True:
                        self.work.discard()
                    elif uri.path in ("/api/slice", "/api/save", "/api/start", "/api/stop"):
                        self.work.start(uri.path.removeprefix("/api/"), data)
                    else:
                        raise WebError(404, "Unknown operation")
                await self.reply(writer, 200, self.work.state)
            else:
                if uri.query or int(headers.get("content-length", "0")) != 0:
                    raise WebError(400, "Unexpected query/body")
                if uri.path == "/api/config":
                    await self.reply(writer, 200, {"token": self.token, "target": f"{self.config.client.host}:{self.config.client.port}",
                        "upload_enabled": self.config.enable_upload, "job_controls_enabled": self.config.enable_job_controls, "slicing_enabled": self.config.slicing is not None,
                        "sliced_upload_enabled": self.config.allow_sliced_upload, "print_limit": PRINT_LIMIT,
                        "model_limit": MODEL_LIMIT, "storage_limit": STORAGE_LIMIT})
                elif uri.path == "/api/state":
                    await self.reply(writer, 200, self.work.state)
                elif uri.path == "/api/artifact":
                    self.work.idle()
                    if not self.work.artifact:
                        raise WebError(404, "No print-file artifact")
                    path = self.work.artifact
                    with path.open("rb") as file:
                        async with asyncio.timeout(30):
                            await self.head(writer, 200, "application/octet-stream", path.stat().st_size,
                                            'Content-Disposition: attachment; filename="artifact' + path.suffix + '"\r\n')
                            while chunk := file.read(65536):
                                writer.write(chunk)
                                await writer.drain()
                elif uri.path in ("/", "/app.js", "/style.css"):
                    name = "index.html" if uri.path == "/" else uri.path[1:]
                    types = {"index.html": "text/html; charset=utf-8", "app.js": "text/javascript; charset=utf-8", "style.css": "text/css; charset=utf-8"}
                    data = (STATIC / name).read_bytes()
                    await self.reply(writer, 200, data, types[name])
                else:
                    raise WebError(404, "Not found")
        except WebError as exc:
            await self.problem(writer, exc.status, str(exc))
        except (ValueError, UnicodeError, RecursionError, asyncio.IncompleteReadError, asyncio.LimitOverrunError):
            await self.problem(writer, 400, "Malformed or incomplete HTTP request")
        except TimeoutError:
            await self.problem(writer, 408, "Request deadline expired; refresh state before retrying")
        except OSError:
            # Storage errors and disconnected HTTP clients never initiate a retry.
            await self.problem(writer, 500, "Local I/O failed; inspect state and private logs")
        finally:
            writer.close()
            try:
                await asyncio.wait_for(writer.wait_closed(), 1)
            except (OSError, TimeoutError):
                writer.transport.abort()
            finally:
                self.clients.discard(task)

    async def problem(self, writer, status, message):
        try:
            await self.reply(writer, status, {"error": message})
        except (OSError, TimeoutError):
            writer.transport.abort()

    async def head(self, writer, status, kind, length, extra=""):
        writer.write((f"HTTP/1.1 {status} Response\r\nContent-Type: {kind}\r\nContent-Length: {length}\r\n"
                      "Connection: close\r\nCache-Control: no-store\r\nX-Content-Type-Options: nosniff\r\n"
                      "Referrer-Policy: no-referrer\r\n"
                      "Content-Security-Policy: default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'\r\n"
                      + extra + "\r\n").encode("ascii"))
        await asyncio.wait_for(writer.drain(), 10)

    async def reply(self, writer, status, data, kind="application/json"):
        if not isinstance(data, bytes):
            data = json.dumps(data, ensure_ascii=True).encode()
        await self.head(writer, status, kind, len(data))
        writer.write(data)
        await asyncio.wait_for(writer.drain(), 10)


def add_web_command(commands):
    cli = commands.add_parser("web", help="local standalone upload page; optional offline Orca slicing")
    cli.add_argument("--listen-host", default="127.0.0.1")
    cli.add_argument("--listen-port", type=int, default=8000)
    cli.add_argument("--data-dir", type=Path, default=Path("web-data"))
    cli.add_argument("--target-host", default="127.0.0.1")
    cli.add_argument("--target-port", type=int, default=8899)
    cli.add_argument("--allow-hardware", action="store_true")
    cli.add_argument("--enable-upload", action="store_true")
    cli.add_argument("--enable-job-controls", action="store_true", help="enable separately confirmed start/cancel (may heat/move)")
    cli.add_argument("--allow-sliced-upload", action="store_true")
    cli.add_argument("--orca")
    for kind in ("machine", "process", "filament"):
        cli.add_argument("--" + kind, type=Path)


def web_main(cli, args):
    try:
        options = [args.get(k) for k in ("machine", "process", "filament")]
        slicing = None
        if any(options) or args.get("orca"):
            slicing = SliceConfig(**{k: args[k] for k in ("machine", "process", "filament", "orca")})
        config = WebConfig(host=args["listen_host"], port=args["listen_port"], data_dir=args["data_dir"],
                           client=ClientConfig(host=args["target_host"], port=args["target_port"], allow_hardware=args["allow_hardware"]),
                           slicing=slicing, enable_upload=args["enable_upload"], enable_job_controls=args["enable_job_controls"],
                           allow_sliced_upload=args["allow_sliced_upload"])
    except ValueError as exc:
        cli.error(str(exc))

    async def run():
        stopped = asyncio.Event()
        loop = asyncio.get_running_loop()
        loop.add_signal_handler(signal.SIGTERM, stopped.set)
        try:
            async with WebServer(config) as server:
                print(f"Open http://{server.authority} (exact URL required)", flush=True)
                print("Private files/captures: " + str(server.work.folder), flush=True)
                print("No automatic connect, start, stop or retries. Loopback may proxy hardware.", flush=True)
                print("Explicit job controls: " + ("ENABLED (may heat/move)" if config.enable_job_controls else "disabled"), flush=True)
                print("Orca: " + ("configured; profiles/toolpaths NOT validated" if slicing else "not configured; Finder Orca profile remains blocked"), flush=True)
                await stopped.wait()
        finally:
            loop.remove_signal_handler(signal.SIGTERM)
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        pass
    except (OSError, ValueError) as exc:
        cli.exit(1, f"Cannot run web page: {exc}\n")
