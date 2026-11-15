"""Local single-slot workbench with opt-in authenticated private-LAN sharing.

Deliberately narrow HTTP/1.1 subset (Content-Length, close after one request).
Not a general purpose web server or an Internet-facing service.
"""

import asyncio
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import dataclass, field, replace
import hashlib
import json
import os
import re
import unicodedata
from pathlib import Path
import secrets
import shutil
import signal
from urllib.parse import parse_qs, urlsplit
import uuid

from .capture import Capture, CaptureError
from .client import ClientConfig, FinderClient, remote_path
from .slicer import SliceConfig, slice_model
from .model_transform import normalize_transform
from .slice_settings import normalize_settings
from .passive_status import status_from_capture
from .active_status import ActiveMonitor
from .manual_controls import VirtualControls, StaleControls
from .web_access import WebAccess, validate_listener

STATIC = Path(__file__).with_name("webstatic")
PRINT_LIMIT = 8 * 1024 * 1024
MODEL_LIMIT = 64 * 1024 * 1024
CAPTURE_LIMIT = 64 * 1024 * 1024
JOB_CAPTURE_LIMIT = 1024 * 1024
STORAGE_LIMIT = 256 * 1024 * 1024
STATIC_FILES = {"/": ("index.html", "text/html; charset=utf-8"), "/style.css": ("style.css", "text/css; charset=utf-8")}
for _name in ("app.js", "manual.js", "preview.js", "toolpath-view.js", "toolpath-worker.js", "model-preview.js", "model-worker.js", "model-transform.js",
              "vendor/three/three.module.min.js", "vendor/three/OrbitControls.js"):
    STATIC_FILES["/" + _name] = (_name, "text/javascript; charset=utf-8")
STATIC_FILES["/vendor/three/LICENSE"] = ("vendor/three/LICENSE", "text/plain; charset=utf-8")


def suggested_name(name):
    """Safe bounded ASCII basename derived from display name, never a path."""
    suffix = ".gcode" if Path(name).suffix.lower() in (".stl", ".3mf") else Path(name).suffix.lower()
    stem = unicodedata.normalize("NFKD", Path(name).stem).encode("ascii", "ignore").decode()
    stem = re.sub(r"[^A-Za-z0-9_. -]", "_", stem)
    stem = re.sub(r"\.{2,}", "_", stem).strip(" .-_") or "model"
    stem = stem[:128-len(suffix)].rstrip(" .")
    result = stem + suffix
    remote_path(result)
    return result


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
        if kind == "slicer_command":
            self.state["slicer_stage"] = fields.get("stage", "")
            if self.state["slicer_stage"] == "slice":
                self.state["slicer_log"] = ""  # UI excerpt only; raw help remains recorded.
        elif kind == "slicer_output":
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
    status_capture: Path | None = None
    enable_monitor: bool = False
    auto_monitor: bool = False
    lan: bool = False
    lan_network: str = "192.168.0.0/16"

    def __post_init__(self):
        if self.auto_monitor and not self.enable_monitor:
            raise ValueError("Automatic monitoring requires enable_monitor")
        if os.name != "posix":
            raise ValueError("The experimental web workbench currently requires POSIX/Linux workspace locking")
        validate_listener(self.host, self.lan, self.lan_network)
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
        self.network_lock = asyncio.Lock()
        self.monitor = None
        self.owned_dummy = False
        self.manual_controls = None
        self.owned_printer = None
        self.manual_capture = ""
        self.model_cache = None
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
                "suggested_name": "", "saved_name": "", "save_id": "", "start_attempted": False, "job_result": "not_requested", "slicer_stage": "", "slice_settings": None,
                "effective_quality": None, "model": False, "source_sha256": "", "source_id": "", "model_transform": None, "start_after_upload": False,
                "save_capture": "", "start_capture": "", "gx_metadata": None, "gx_unavailable": "Slice a model first", "gx_generated": False}

    def capacity(self, reserve):
        if self.monitor and self.monitor.capture and not self.monitor.capture.closed:
            reserve += max(0, self.monitor.max_bytes - self.monitor.capture.written) + 1024 * 1024
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
        if suffix not in (".stl", ".3mf", ".gx", ".gcode", ".g"):
            raise WebError(400, "Choose STL, 3MF, GX, G-code or G")
        limit = MODEL_LIMIT if suffix in (".stl", ".3mf") else PRINT_LIMIT
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
            self.artifact = path if suffix not in (".stl", ".3mf") else None
            self.state.update(phase="model_ready" if suffix in (".stl", ".3mf") else "file_ready",
                              size=length, sha256=digest.hexdigest(), source_sha256=digest.hexdigest(),
                              model=suffix in (".stl", ".3mf"), source_id=uuid.uuid4().hex, artifact=self.artifact is not None,
                              suggested_name=suggested_name(name))
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
        self.model_cache = None
        self.state = self.empty()

    async def model_geometry(self):
        """Input geometry only; never a slicer/client. Source identity survives Slice."""
        self.idle()
        if not self.source or not self.state["model"]:
            raise WebError(404, "No STL/3MF source model")
        if self.source.suffix == ".stl":
            return self.source, 0
        if self.model_cache and self.model_cache[0].is_file():
            return self.model_cache
        self.model_cache = None
        from .model_3mf import MAX_TRIANGLES
        max_derived = min(MODEL_LIMIT, 84 + MAX_TRIANGLES * 50)
        self.capacity(max_derived + 4096)
        previous = self.state["phase"]
        self.state.update(busy=True, phase="model_preview")
        destination = self.slot / "model-preview.stl"
        process = None
        try:
            import sys
            process = await asyncio.create_subprocess_exec(
                sys.executable, "-m", "finderlab.model_3mf", str(self.source), str(destination),
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL, start_new_session=True,
                cwd=Path(__file__).resolve().parents[1])
            async with asyncio.timeout(20):
                output, _ = await process.communicate()
            if process.returncode != 0 or len(output) > 512 * 1024:
                raise WebError(422, "3MF model preview failed or exceeded resources; export mesh-only STL if unsupported")
            info = json.loads(output)
            if not destination.is_file() or not 0 < destination.stat().st_size <= max_derived:
                raise WebError(422, "Invalid geometry preview output")
            self.model_cache = destination, info["zero_area_facets_skipped"]
            return self.model_cache
        finally:
            try:
                if process is not None and process.returncode is None:
                    try: os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError: pass
                    await process.wait()
                if self.model_cache is None:
                    destination.unlink(missing_ok=True)
            finally:
                self.state.update(busy=False, phase=previous)

    def start(self, operation, data):
        self.idle()
        if operation not in ("slice", "save", "start", "stop", "gx"):
            raise WebError(400, "Unknown operation")
        allowed = ({"confirm", "remote_name", "start_after_upload", "artifact_sha256", "source_id"} if operation == "save" else {"confirm", "save_id"} if operation == "start"
                   else {"confirm", "settings", "transform", "source_sha256", "source_id"} if operation == "slice"
                   else {"confirm", "artifact_sha256", "source_id"} if operation == "gx" else {"confirm"})
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
            self.capacity(JOB_CAPTURE_LIMIT + 1024 * 1024)
            if operation == "start":
                self.state["start_attempted"] = True
            self.state.update(busy=True, phase="connecting", error="", warning="", capture="")
            self.task = asyncio.create_task(self._operation(operation, data))
            return
        if self.source is None:
            raise WebError(409, "Choose a file first")
        if operation == 'gx':
            if (not self.config.slicing or not self.state['sliced'] or not self.artifact or self.state['saved']
                    or self.state['phase'] == 'unknown' or self.state['gx_generated'] or not self.state['gx_metadata']):
                raise WebError(409,'GX needs an unsaved successful model Slice with supported metadata; existing print files cannot be repackaged here')
            if data.get('artifact_sha256') != self.state['sha256'] or data.get('source_id') != self.state['source_id']:
                raise WebError(409,'Artifact/slot changed; refresh before creating GX')
            self.capacity(PRINT_LIMIT + 2*1024*1024)
            self.state.update(busy=True,phase='gx_export',error='',warning='')
            self.task=asyncio.create_task(self._operation(operation,data));return
        if operation == "slice":
            if not self.config.slicing:
                raise WebError(409, "Orca is not configured; no validated Finder profile ships with this page")
            if self.source.suffix not in (".stl", ".3mf") or self.artifact:
                raise WebError(409, "Slicing needs a new STL/3MF; discard before slicing another version")
            try:
                settings = normalize_settings(data.get("settings"))
                transform = normalize_transform(data.get("transform"))
            except ValueError as exc:
                raise WebError(400, str(exc)) from exc
            if (transform is not None or "source_sha256" in data) and data.get("source_sha256") != self.state["source_sha256"]:
                raise WebError(409, "Source model changed; reload before applying transforms")
            if "source_id" in data and data["source_id"] != self.state["source_id"]:
                raise WebError(409, "Source slot changed; reload before slicing")
        else:
            if type(data.get("start_after_upload", False)) is not bool:
                raise WebError(400, "start_after_upload must be a boolean")
            if data.get("start_after_upload", False) and not self.config.enable_job_controls:
                raise WebError(409, "Start after upload requires server --enable-job-controls")
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
            combined = data.get("start_after_upload", False)
            if (combined or "artifact_sha256" in data) and data.get("artifact_sha256") != self.state["sha256"]:
                raise WebError(409, "Selected print artifact changed; refresh before saving/starting")
            if (combined or "source_id" in data) and data.get("source_id") != self.state["source_id"]:
                raise WebError(409, "Selected file slot changed; refresh before saving/starting")
            name = data.get("remote_name")
            if not isinstance(name, str):
                raise WebError(400, "An ASCII remote basename is required")
            try:
                remote_path(name)
            except ValueError as exc:
                raise WebError(400, str(exc)) from exc
            if self.state["sliced"] and ((self.state['gx_generated'] and Path(name).suffix.lower() != '.gx')
                                         or (not self.state['gx_generated'] and Path(name).suffix.lower() not in ('.gcode','.g'))):
                raise WebError(400, "Selected generated format requires its actual extension; renaming is not conversion")
        self.capacity(CAPTURE_LIMIT + PRINT_LIMIT + (JOB_CAPTURE_LIMIT if data.get("start_after_upload") else 0) + 1024 * 1024)
        self.state.update(busy=True, phase="slicing" if operation == "slice" else "connecting", error="", warning="", capture="")
        if operation == "save":
            self.state["start_after_upload"] = data.get("start_after_upload", False)
            if self.state["start_after_upload"]:
                self.state["job_result"] = "start_not_sent"
        if operation == "slice":
            self.state["slicer_log"] = ""
            self.state["slicer_stage"] = ""
            self.state["slice_settings"] = settings
            self.state["model_transform"] = transform
            self.state["effective_quality"] = None
        self.task = asyncio.create_task(self._operation(operation, data))

    def manual_snapshot(self):
        enabled = self.manual_controls is not None and self.owned_printer is not None
        job_active = bool(self.owned_printer and self.owned_printer.active_file)
        return {"enabled": enabled, "virtual_only": True, "busy": self.state["busy"], "job_active": job_active,
                "blocked": self.state["phase"] == "unknown", "capture": self.manual_capture,
                "state": self.manual_controls.snapshot() if enabled else None,
                "message": "Virtual rehearsal only; no G-code or heater/motion/light commands are sent. Counters are NOT position feedback."
                           if enabled else "Physical manual controls are locked pending step-mode, extrusion and reply-format verification. Use an owned dummy to rehearse."}

    def manual_action(self, data):
        # Being loopback, having upload/job flags or claiming owned_dummy in JSON is NOT authorization.
        if self.manual_controls is None or self.owned_printer is None:
            raise WebError(409, "Manual controls are owned-dummy rehearsal only; hardware/proxy controls remain locked")
        self.idle()
        if self.owned_printer.active_file or self.state["phase"] == "unknown":
            raise WebError(409, "Manual rehearsal blocked during a virtual job or unknown local printer result")
        try:
            candidate = self.manual_controls.prepare(data)
        except StaleControls as exc:
            raise WebError(409, str(exc)) from exc
        except ValueError as exc:
            raise WebError(400, str(exc)) from exc
        self.capacity(128 * 1024)
        capture = Capture(self.folder / "captures", "manual-virtual", max_bytes=64 * 1024, max_sessions=1,
                          metadata={"interface": "standalone-web", "operation": "manual_virtual", "target_kind": "owned_dummy",
                                    "start_requested": False, "wire_commands_sent": False})
        try:
            capture.event("manual_virtual_intent", intent=data, before=self.manual_controls.snapshot(), candidate=candidate)
        finally:
            capture.close()
        if capture.failed:
            raise CaptureError("Manual rehearsal recording incomplete; no counter/light change committed")
        # No await or network calls between validation and this commit: duplicate revisions cannot race.
        self.manual_controls.state = candidate
        self.manual_capture = capture.path.name
        return self.manual_snapshot()

    def toggle_monitor(self, data):
        if set(data) != {"enabled", "confirm"} or type(data["enabled"]) is not bool or data["confirm"] is not True:
            raise WebError(400, "Monitoring needs explicit confirmation and a boolean enabled flag")
        if not self.config.enable_monitor:
            raise WebError(409, "Active polling requires server --enable-monitor; passive observation stays read-only")
        if data["enabled"]:
            self.idle()
            if self.monitor and self.monitor.task and not self.monitor.task.done():
                raise WebError(409, "Monitor already running or stopping")
            self.capacity(CAPTURE_LIMIT + 1024 * 1024)
            self.monitor = ActiveMonitor(self.config.client, self.folder, self.network_lock,
                                         lambda: self.state["busy"], emulated=self.owned_dummy)
            self.monitor.start()
        elif self.monitor:
            self.monitor.request_stop()  # Stop local polling, NEVER a printer cancel.

    @asynccontextmanager
    async def printer_session(self, capture):
        async with self.network_lock:
            if self.monitor:
                await self.monitor.release_client()
            async with FinderClient(self.config.client, capture=capture) as client:
                yield client

    async def _operation(self, operation, data):
        capture = None
        network = False
        combined = operation == "save" and data.get("start_after_upload", False)
        confirmed = None
        follow_start = False
        try:
            capture = WebCapture(self.folder / "captures", "slice" if operation == "slice" else "gx" if operation == 'gx' else "client", state=self.state,
                              max_bytes=JOB_CAPTURE_LIMIT if operation in ("start", "stop", "gx") else CAPTURE_LIMIT, max_sessions=1,
                              metadata={"operation": operation, "start_requested": operation == "start" or combined,
                                        "start_after_upload": combined or data.get("_after_upload", False),
                                        "source_id": self.state["source_id"], "expected_artifact_sha256": data.get("artifact_sha256"),
                                        "interface": "standalone-web",
                                        "target_kind": "owned_dummy" if self.owned_dummy else "configured_endpoint"})
            self.state["capture"] = str(capture.path)
            if operation in ("save", "start"):
                self.state[operation + "_capture"] = str(capture.path)
            if operation == "start":
                capture.manifest["metadata"].update(saved_name=self.state["saved_name"], save_id=self.state["save_id"],
                                                       save_capture=self.state["save_capture"], saved_sha256=self.state["sha256"])
            if operation == 'gx':
                from .gx_export import export_gx
                destination=self.artifact.with_suffix('.gx')
                info=await export_gx(self.artifact,self.source,destination,self.config.slicing,capture=capture,
                                     metadata=self.state['gx_metadata'],transform=self.state['model_transform'],
                                     expected_gcode_sha256=data['artifact_sha256'],expected_model_sha256=self.state['source_sha256'])
                self.artifact=destination
                self.state.update(phase='review',gx_generated=True,size=info['size'],sha256=info['sha256'],
                                  suggested_name=Path(self.state['suggested_name']).with_suffix('.gx').name,
                                  warning='Experimental GX envelope/thumbnail; printer display/firmware acceptance not verified. G-code body unchanged.')
            elif operation == "slice":
                result = await slice_model(self.source, self.slot / self.state["suggested_name"], self.config.slicing,
                                           capture=capture, settings=self.state["slice_settings"], transform=self.state["model_transform"])
                self.artifact = result.path
                self.state.update(phase="review", sliced=True, artifact=True, size=result.size, sha256=result.sha256,
                                  effective_quality=capture.manifest["metadata"].get("effective_quality"),
                                  gx_metadata=capture.manifest['metadata'].get('gx_metadata'),
                                  gx_unavailable=capture.manifest['metadata'].get('gx_unavailable','Unsupported metadata'))
                capture.manifest["metadata"]["slicing_confirmed"] = True
            else:
                network = True
                async with asyncio.timeout(900):
                    async with self.printer_session(capture) as client:
                        capture.manifest.update(model="Flashforge Finder (emulated)" if self.owned_dummy else "Flashforge Finder", firmware="V1.5 20170419")
                        if operation == "save":
                            self.state["phase"] = "uploading"
                            def progress(count, size):
                                self.state.update(acknowledged=count, size=size)
                            result = await client.upload(self.artifact, remote_name=data["remote_name"], progress=progress)
                            self.state.update(phase="saved", saved=True, sha256=result.sha256,
                                              saved_name=result.path.removeprefix("0:/user/"), save_id=uuid.uuid4().hex)
                            capture.manifest["metadata"].update(upload_confirmed=True, remote_path=result.path, save_id=self.state["save_id"],
                                                                uploaded_sha256=result.sha256)
                            confirmed = (self.state["save_id"], self.state["saved_name"], self.state["sha256"])
                            if "artifact_sha256" in data and result.sha256 != data["artifact_sha256"]:
                                raise ValueError("Saved bytes differ from selected artifact; start blocked, inspect the source")
                        elif operation == "start":
                            await client.start(self.state["saved_name"], confirm=True)
                            self.state.update(phase="start_acknowledged", job_result="start_acknowledged")
                            capture.manifest["metadata"]["start_acknowledged"] = True
                        else:
                            await client.stop(confirm=True)
                            self.state.update(phase="cancel_acknowledged", job_result="cancel_acknowledged")
                            capture.manifest["metadata"]["stop_acknowledged"] = True
                    if client.cleanup_error:
                        if self.monitor:
                            self.monitor.request_stop()
                        self.state["warning"] = "Operation confirmed, but release failed: " + client.cleanup_error
        except BaseException as exc:
            if network and self.monitor:
                self.monitor.request_stop()  # Never reconnect automatically after uncertain printer I/O.
            self.state.update(phase="unknown" if network else "failed", error=str(exc) or type(exc).__name__)
            if operation in ("start", "stop"):
                self.state["job_result"] = operation + "_unknown" if network else "not_sent"
            if capture and not capture.failed and not capture.closed:
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
                if network and self.monitor:
                    self.monitor.request_stop()
                self.state.update(phase="unknown" if network else "failed", error="Recording failed: " + str(exc))
            finally:
                # Do not release the local operation slot between save and start.
                # A fully finalized save recording AND healthy release are required.
                follow_start = bool(combined and confirmed and capture and capture.closed and not capture.failed
                                    and capture.manifest.get("complete")
                                    and self.state["saved"] and self.state["phase"] == "saved"
                                    and not self.state["warning"] and not self.state["error"]
                                    and confirmed == (self.state["save_id"], self.state["saved_name"], self.state["sha256"]))
                if follow_start:
                    self.state.update(start_attempted=True, phase="connecting", job_result="start_pending")
                else:
                    self.state["busy"] = False
        if follow_start:
            # New firmware-gated session, fresh READY inside client.start(), exact
            # saved name/identity. Never repeat on failure or add an automatic stop.
            await self._operation("start", {"confirm": True, "save_id": confirmed[0], "_after_upload": True})

    async def close(self):
        if self.task and not self.task.done():
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
        if self.monitor:
            await self.monitor.close()
        self.lock.close()


class WebServer:
    def __init__(self, config, *, owned_dummy=None):
        self.config = config
        self.work = None
        self.token = secrets.token_urlsafe(32)
        self.access = WebAccess(config.host, config.lan, config.lan_network)
        self.server = None
        self.clients = set()
        self.address = None
        self.owned_dummy = owned_dummy

    async def __aenter__(self):
        self.work = Workbench(self.config)
        self.work.owned_dummy = self.owned_dummy is not None
        self.work.owned_printer = self.owned_dummy
        if self.owned_dummy is not None:
            self.work.manual_controls = VirtualControls()
        try:
            self.server = await asyncio.start_server(self.handle, self.config.host, self.config.port, limit=16384)
            self.address = self.server.sockets[0].getsockname()[:2]
            if self.config.auto_monitor:
                try:
                    self.work.toggle_monitor({"enabled": True, "confirm": True})
                except (OSError, ValueError) as exc:
                    # Keep UI accessible for storage/preflight failure, without retrying.
                    self.work.monitor = ActiveMonitor(self.config.client, self.work.folder, self.work.network_lock,
                                                       lambda: self.work.state["busy"], emulated=self.work.owned_dummy)
                    self.work.monitor.error = str(exc)
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
            # Only socket peer identity counts. Never trust Forwarded/X-Forwarded-For.
            if not self.access.allows_peer(writer.get_extra_info("peername")):
                raise WebError(403, "Client address is not allowed")
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
                raise WebError(403, "Use the exact IP URL printed by the server")
            if not self.access.authenticated(headers.get("authorization", "")):
                await self.reply(writer, 401, {"error": "LAN password required"},
                                 extra='WWW-Authenticate: Basic realm="Finder workbench", charset="UTF-8"\r\n')
                return
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
                    if uri.path == "/api/manual":
                        await self.reply(writer, 200, self.work.manual_action(data))
                        return
                    if uri.path == "/api/monitor":
                        self.work.toggle_monitor(data)
                        await self.reply(writer, 200, self.work.monitor.report() if self.work.monitor else {"monitor_running": False})
                        return
                    if uri.path == "/api/discard" and set(data) == {"confirm"} and data["confirm"] is True:
                        self.work.discard()
                    elif uri.path in ("/api/slice", "/api/save", "/api/start", "/api/stop", "/api/gx"):
                        self.work.start(uri.path.removeprefix("/api/"), data)
                    else:
                        raise WebError(404, "Unknown operation")
                await self.reply(writer, 200, self.work.state)
            else:
                if (uri.query and uri.path != '/api/gx-thumbnail') or int(headers.get("content-length", "0")) != 0:
                    raise WebError(400, "Unexpected query/body")
                if uri.path == "/api/config":
                    await self.reply(writer, 200, {"token": self.token, "target": f"{self.config.client.host}:{self.config.client.port}",
                        "upload_enabled": self.config.enable_upload, "job_controls_enabled": self.config.enable_job_controls, "slicing_enabled": self.config.slicing is not None,
                        "priming_review_enabled": bool(self.config.slicing and self.config.slicing.check_priming),
                        "sliced_upload_enabled": self.config.allow_sliced_upload, "print_limit": PRINT_LIMIT,
                        "model_limit": MODEL_LIMIT, "storage_limit": STORAGE_LIMIT,
                        "passive_status_enabled": self.config.status_capture is not None,
                        "active_monitor_enabled": self.config.enable_monitor, "auto_monitor": self.config.auto_monitor,
                        "manual_virtual_enabled": self.work.manual_controls is not None,
                        "lan_mode": self.config.lan, "owned_dummy": self.owned_dummy is not None})
                elif uri.path == "/api/printer-status":
                    await self.reply(writer, 200, self.work.monitor.report() if self.work.monitor else
                                     status_from_capture(self.config.status_capture, self.config.client.host, self.config.client.port))
                elif uri.path == "/api/manual-state":
                    await self.reply(writer, 200, self.work.manual_snapshot())
                elif uri.path == "/api/state":
                    await self.reply(writer, 200, self.work.state)
                elif uri.path == "/api/model":
                    # This read can prepare a bounded private 3MF derivative: require
                    # the per-run token to prevent cross-site image/GET work triggers.
                    if not secrets.compare_digest(headers.get("x-finder-token", ""), self.token):
                        raise WebError(403, "Reload the page before requesting model preview")
                    self.work.idle()
                    tag = '"' + self.work.state["source_sha256"] + '"'
                    if "if-match" in headers and headers["if-match"] != tag:
                        raise WebError(412, "Source model changed; reload model preview")
                    path, skipped = await self.work.model_geometry()
                    with path.open("rb") as file:
                        async with asyncio.timeout(30):
                            await self.head(writer, 200, "application/octet-stream", path.stat().st_size,
                                            'ETag: ' + tag + '\r\nX-Skipped-Facets: ' + str(skipped) + '\r\n')
                            while chunk := file.read(65536):
                                writer.write(chunk); await writer.drain()
                elif uri.path == '/api/gx-thumbnail':
                    self.work.idle()
                    if not self.work.artifact or not self.work.state['gx_generated']:
                        raise WebError(404,'No generated GX thumbnail')
                    # Hash-bound URL avoids showing an older slot during another tab's edits.
                    if uri.query != 'v='+self.work.state['sha256']:
                        raise WebError(412,'GX identity changed; refresh before viewing thumbnail')
                    with self.work.artifact.open('rb') as source:
                        prefix=source.read(14512)
                    if len(prefix)!=14512 or prefix[:12]!=b'xgcode 1.0\n\0' or prefix[58:60]!=b'BM':
                        raise WebError(422,'Generated thumbnail is unavailable')
                    await self.reply(writer,200,prefix[58:14512],'image/bmp')
                elif uri.path == "/api/artifact":
                    self.work.idle()
                    if not self.work.artifact:
                        raise WebError(404, "No print-file artifact")
                    etag = '"' + self.work.state["sha256"] + '"'
                    if "if-match" in headers and headers["if-match"] != etag:
                        raise WebError(412, "Artifact changed; refresh preview before loading")
                    path = self.work.artifact
                    with path.open("rb") as file:
                        async with asyncio.timeout(30):
                            await self.head(writer, 200, "application/octet-stream", path.stat().st_size,
                                            'Content-Disposition: attachment; filename="' + self.work.state["suggested_name"] + '"\r\nETag: ' + etag + '\r\n')
                            while chunk := file.read(65536):
                                writer.write(chunk)
                                await writer.drain()
                elif uri.path in STATIC_FILES:
                    name, kind = STATIC_FILES[uri.path]
                    data = (STATIC / name).read_bytes()
                    await self.reply(writer, 200, data, kind)
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
                      "Content-Security-Policy: default-src 'none'; script-src 'self'; worker-src 'self'; style-src 'self'; img-src 'self'; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'\r\n"
                      + extra + "\r\n").encode("ascii"))
        await asyncio.wait_for(writer.drain(), 10)

    async def reply(self, writer, status, data, kind="application/json", *, extra=""):
        if not isinstance(data, bytes):
            data = json.dumps(data, ensure_ascii=True).encode()
        await self.head(writer, status, kind, len(data), extra)
        writer.write(data)
        await asyncio.wait_for(writer.drain(), 10)


@asynccontextmanager
async def serve_workbench(config, *, dummy=False):
    """Optional owned simulator: never treat an existing loopback port as safe."""
    async with AsyncExitStack() as stack:
        printer = None
        if dummy:
            from .simulator import MockConfig, MockPrinter
            printer = await stack.enter_async_context(MockPrinter(MockConfig(host="127.0.0.1", port=0)))
            config = replace(config, client=ClientConfig(host="127.0.0.1", port=printer.address[1]),
                             enable_upload=True, allow_sliced_upload=True, enable_job_controls=True, status_capture=None)
        server = await stack.enter_async_context(WebServer(config, owned_dummy=printer))
        server.owned_dummy = printer
        server.work.owned_dummy = printer is not None
        yield server


def add_web_command(commands):
    cli = commands.add_parser("web", help="local standalone upload page; optional offline Orca slicing")
    cli.add_argument("--listen-host", default="127.0.0.1")
    cli.add_argument("--listen-port", type=int, default=8000)
    cli.add_argument("--lan", action="store_true", help="explicit private-LAN sharing with per-run Basic password; HTTP is NOT encrypted")
    cli.add_argument("--lan-network", default="192.168.0.0/16", help="allowed IPv4 CIDR within 192.168/16; socket peers only")
    cli.add_argument("--data-dir", type=Path, default=Path("web-data"))
    cli.add_argument("--status-capture", type=Path, help="read-only existing proxy run/root for passive status; never polls a printer")
    cli.add_argument("--target-host", default="127.0.0.1")
    cli.add_argument("--target-port", type=int, default=8899)
    cli.add_argument("--dummy", action="store_true", help="own a fresh ephemeral dummy and enable upload-only to it; no hardware target")
    cli.add_argument("--allow-hardware", action="store_true")
    cli.add_argument("--enable-upload", action="store_true")
    cli.add_argument("--enable-monitor", action="store_true", help="permit active status polling; requires sole client ownership")
    cli.add_argument("--auto-monitor", action="store_true", help="start status polling on server startup; implies --enable-monitor, opens a printer connection")
    cli.add_argument("--enable-job-controls", action="store_true", help="enable separately confirmed start/cancel (may heat/move)")
    cli.add_argument("--allow-sliced-upload", action="store_true")
    cli.add_argument("--orca")
    cli.add_argument("--check-priming", action="store_true", help="experimental native-skirt/nominal first-layer guard; no physical safety guarantee")
    for kind in ("machine", "process", "filament"):
        cli.add_argument("--" + kind, type=Path)


def web_main(cli, args):
    try:
        if args["dummy"] and (args["target_host"] != "127.0.0.1" or args["target_port"] != 8899 or args["allow_hardware"] or args["enable_job_controls"]):
            raise ValueError("--dummy owns its endpoint; do not supply target/hardware/job-control options")
        options = [args.get(k) for k in ("machine", "process", "filament")]
        slicing = None
        if any(options) or args.get("orca") or args.get("check_priming"):
            slicing = SliceConfig(**{k: args[k] for k in ("machine", "process", "filament", "orca")},
                                  check_priming=args.get("check_priming", False))
        config = WebConfig(host=args["listen_host"], port=args["listen_port"], data_dir=args["data_dir"],
                           lan=args["lan"], lan_network=args["lan_network"],
                           client=ClientConfig(host=args["target_host"], port=args["target_port"], allow_hardware=args["allow_hardware"]),
                           slicing=slicing, enable_upload=args["enable_upload"], enable_job_controls=args["enable_job_controls"],
                           allow_sliced_upload=args["allow_sliced_upload"], status_capture=args["status_capture"], enable_monitor=args["enable_monitor"] or args["auto_monitor"], auto_monitor=args["auto_monitor"])
    except ValueError as exc:
        cli.error(str(exc))

    async def run():
        stopped = asyncio.Event()
        loop = asyncio.get_running_loop()
        loop.add_signal_handler(signal.SIGTERM, stopped.set)
        try:
            async with serve_workbench(config, dummy=args["dummy"]) as server:
                print(f"Open http://{server.authority} (exact URL required)", flush=True)
                if config.lan:
                    print(f"LAN sharing: allowed {server.access.network} plus local IPv4. HTTP IS NOT ENCRYPTED; trusted home network only.", flush=True)
                    print("Login username: finder", flush=True)
                    print("Login password (new each restart; share privately): " + server.access.password, flush=True)
                    print("All logged-in users share one workspace/printer and can use enabled controls. No router port forwarding/public proxy.", flush=True)
                print("Private files/captures: " + str(server.work.folder), flush=True)
                if server.owned_dummy:
                    print(f"Owned fresh dummy: {server.owned_dummy.address}. RAM-only virtual files; no G-code execution.", flush=True)
                    print("Save and confirmed virtual Start/Cancel target only this new dummy. No existing listener/proxy is used.", flush=True)
                else:
                    print("Automatic status connection ENABLED; close FlashPrint/other clients." if server.config.auto_monitor else "No automatic printer connection.", flush=True)
                    print("No automatic print start/cancel or error retries. Loopback may proxy hardware.", flush=True)
                print("Explicit job controls: " + ("VIRTUAL ONLY" if server.owned_dummy else "ENABLED (may heat/move)" if server.config.enable_job_controls else "disabled"), flush=True)
                print("Orca: " + ("configured; profiles/toolpaths NOT validated" if slicing else "not configured; no print-approved Finder profile is provided"), flush=True)
                await stopped.wait()
        finally:
            loop.remove_signal_handler(signal.SIGTERM)
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        pass
    except (OSError, ValueError) as exc:
        cli.exit(1, f"Cannot run web page: {exc}\n")
