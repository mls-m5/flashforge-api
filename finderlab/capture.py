"""Version 1 local byte-stream captures. Never uploads data anywhere."""

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import time
import uuid

from . import __version__

DIRECTIONS = ("client_to_server", "server_to_client")


class CaptureError(OSError):
    """Recording failed: stop forwarding rather than silently lose evidence."""


def utc_now():
    return datetime.now(timezone.utc).isoformat()


class Capture:
    def __init__(self, root, mode, *, metadata=None, max_bytes=256 * 1024 * 1024,
                 max_sessions=1000, flashprint_version=None, experiment_id=None,
                 model=None, firmware=None):
        if max_bytes <= 0 or max_sessions <= 0:
            raise ValueError("capture limits must be positive")
        capture_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ-") + uuid.uuid4().hex[:12]
        root = Path(root)
        root.mkdir(parents=True, exist_ok=True)
        self.path = root / capture_id
        self.path.mkdir(mode=0o700)
        self.max_bytes = max_bytes
        self.max_sessions = max_sessions
        self.written = 0
        self.failed = False
        self.closed = False
        self.seq = 0
        self.start = time.monotonic_ns()
        self.sessions = []
        self.manifest = {
            "v": 1, "capture_id": capture_id, "tool_version": __version__,
            "mode": mode, "started_utc": utc_now(), "complete": False,
            "os": platform.platform(), "model": model, "firmware": firmware,
            "flashprint_version": flashprint_version, "experiment_id": experiment_id,
            "max_capture_bytes": max_bytes, "max_sessions": max_sessions,
            "metadata": metadata or {}, "sessions": [],
        }
        self.events = None
        self.log = None
        try:
            self._manifest()
            self.events = (self.path / "events.jsonl").open("wb", buffering=0)
            self.log = (self.path / "traffic.log").open("wb", buffering=0)
        except OSError:
            if self.events:
                self.events.close()
            raise

    def _manifest(self):
        # Keep the previous incomplete manifest intact if replacement fails.
        temporary = self.path / "manifest.tmp"
        temporary.write_text(json.dumps(self.manifest, indent=2) + "\n", encoding="utf-8")
        temporary.replace(self.path / "manifest.json")

    def _write(self, file, data):
        if self.failed or self.closed:
            raise CaptureError("capture is incomplete or closed")
        try:
            if self.written + len(data) > self.max_bytes:
                raise CaptureError("capture byte limit reached")
            if file.write(data) != len(data):
                raise CaptureError("short capture write")
            self.written += len(data)
        except OSError as exc:
            self.failed = True
            raise CaptureError(f"Cannot record capture: {exc}") from exc

    def event(self, kind, session_id=None, **fields):
        self.seq += 1
        record = {
            "v": 1, "seq": self.seq, "session_id": session_id, "type": kind,
            "utc": utc_now(), "monotonic_ns": time.monotonic_ns() - self.start,
            **fields,
        }
        encoded = json.dumps(record, ensure_ascii=True, separators=(",", ":")).encode() + b"\n"
        self._write(self.events, encoded)
        summary = f"{record['utc']} {session_id or '-'} {kind} {json.dumps(fields, ensure_ascii=True)}\n"
        self._write(self.log, summary.encode())
        return self.seq

    def session(self, **metadata):
        if self.failed or self.closed:
            raise CaptureError("capture is incomplete or closed")
        if len(self.sessions) >= self.max_sessions:
            self.failed = True
            raise CaptureError("capture session limit reached")
        session = CaptureSession(self, f"s{len(self.sessions) + 1:04d}")
        self.sessions.append(session)
        self.event("connection_open", session.id, **metadata)
        return session

    def close(self):
        if self.closed:
            return
        try:
            for session in self.sessions:
                try:
                    session.close("capture_shutdown")
                except OSError:
                    # Still close every other raw file if this close/event fails.
                    self.failed = True
            if not self.failed:
                self.event("capture_end")
        except CaptureError:
            self.failed = True
        finally:
            self.closed = True
            self.events.close()
            self.log.close()
        self.manifest.update(
            complete=not self.failed, ended_utc=utc_now(),
            recorded_bytes=self.written,
            sessions=[s.summary for s in self.sessions],
        )
        try:
            self._manifest()
        except OSError as exc:
            self.failed = True
            raise CaptureError(f"Cannot finalize capture manifest: {exc}") from exc


class CaptureSession:
    def __init__(self, capture, session_id):
        self.capture = capture
        self.id = session_id
        self.closed = False
        self.files = {}
        self.hashes = {d: hashlib.sha256() for d in DIRECTIONS}
        self.offsets = {d: 0 for d in DIRECTIONS}
        self.summary = {"session_id": self.id, "closed": False, "streams": {}}
        directory = capture.path / "sessions" / self.id
        try:
            directory.mkdir(parents=True)
            for direction in DIRECTIONS:
                filename = direction.replace("_", "-") + ".bin"
                self.files[direction] = (directory / filename).open("wb", buffering=0)
        except OSError as exc:
            for file in self.files.values():
                file.close()
            capture.failed = True
            raise CaptureError(f"Cannot open session streams: {exc}") from exc

    def event(self, kind, **fields):
        return self.capture.event(kind, self.id, **fields)

    def data(self, direction, data):
        offset = self.offsets[direction]
        self.capture._write(self.files[direction], data)
        self.offsets[direction] += len(data)
        self.hashes[direction].update(data)
        return self.event(
            "data", direction=direction, stream_offset=offset, length=len(data),
            preview=repr(data[:256]), preview_truncated=len(data) > 256,
        )

    def close(self, reason):
        if self.closed:
            return
        self.closed = True
        for direction, file in self.files.items():
            file.close()
            self.summary["streams"][direction] = {
                "length": self.offsets[direction],
                "sha256": self.hashes[direction].hexdigest(),
            }
        self.summary.update(closed=True, reason=reason)
        if not self.capture.failed:
            self.event("connection_close", reason=reason)
