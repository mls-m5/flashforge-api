"""Conservative Finder V1.5 client. Upload, start and stop are separate actions."""

import asyncio
from dataclasses import dataclass
import hashlib
import ipaddress
import logging
import math
import os
from pathlib import Path
import re
import stat

from .capture import Capture
from .protocol.upload import BLOCK_SIZE, encode_frame

LOG = logging.getLogger(__name__)
SUPPORTED_SUFFIXES = frozenset({".gx", ".gcode", ".g"})
FORMAT_DESCRIPTION = ".gx, .gcode or .g"


class ClientError(RuntimeError):
    """No automatic retry is safe after this error."""


class ResultUnknown(ClientError):
    """A save/start/stop was attempted but its success was not confirmed."""


@dataclass(frozen=True)
class ClientConfig:
    host: str = "127.0.0.1"
    port: int = 8899
    timeout: float = 15.0
    connect_timeout: float = 8.0
    save_timeout: float = 30.0
    allow_hardware: bool = False
    max_file_size: int = 8 * 1024 * 1024
    max_line_size: int = 4096
    max_reply_size: int = 65536

    def __post_init__(self):
        address = ipaddress.ip_address(self.host)
        if not address.is_loopback and not self.allow_hardware:
            raise ValueError("Non-loopback targets require --allow-hardware and physical supervision")
        if not 1 <= self.port <= 65535:
            raise ValueError("port must be between 1 and 65535")
        for name in ("timeout", "connect_timeout", "save_timeout"):
            if not math.isfinite(getattr(self, name)) or getattr(self, name) <= 0:
                raise ValueError(f"{name} must be finite and positive")
        for name in ("max_file_size", "max_line_size", "max_reply_size"):
            if getattr(self, name) <= 0:
                raise ValueError(f"{name} must be positive")


def remote_path(name: str) -> str:
    if (not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_. -]{0,127}", name)
            or ".." in name or name.endswith(" ") or Path(name).suffix.lower() not in SUPPORTED_SUFFIXES):
        raise ValueError(f"Remote name must be an ASCII {FORMAT_DESCRIPTION} basename (no paths/control characters; internal spaces allowed)")
    return "0:/user/" + name


def validate_file(path, max_size):
    path = Path(path)
    if path.suffix.lower() not in SUPPORTED_SUFFIXES or not path.is_file():
        raise ValueError(f"Choose an existing regular {FORMAT_DESCRIPTION} file")
    if not 0 < path.stat().st_size <= max_size:
        raise ValueError(f"File must contain 1–{max_size} bytes")
    return path


@dataclass(frozen=True)
class UploadResult:
    path: str
    size: int
    sha256: str


class FinderClient:
    """One serialized session. Failed/uncertain sessions cannot be reused.

    The tested firmware is V1.5 20170419. No discovery, retries, automatic start,
    automatic stop or GX conversion. A loopback endpoint may itself be a hardware
    proxy: the address guard is a precaution, not proof that a target is virtual.
    """

    def __init__(self, config: ClientConfig | None = None, *, capture: Capture | None = None):
        self.config = config or ClientConfig()
        self.capture = capture
        self.record = None
        self.reader = None
        self.writer = None
        self.buffer = bytearray()
        self.info = ()
        self.cleanup_error = None
        self._claimed = False
        self._healthy = False
        self._command_mode = True
        self._lock = asyncio.Lock()

    async def __aenter__(self):
        if self.writer is not None:
            raise ClientError("Client is already connected; create a new session")
        try:
            self.reader, self.writer = await asyncio.wait_for(
                asyncio.open_connection(self.config.host, self.config.port), self.config.connect_timeout,
            )
            if self.capture:
                self.record = self.capture.session(
                    peer=self.writer.get_extra_info("peername"), local=self.writer.get_extra_info("sockname"),
                )
            reply = await self._command("M601 S1")
            if reply != (b"Control Success.",):
                raise ClientError("Control was not granted by the expected Finder protocol")
            self._claimed = True
            self.info = await self._command("M115")
            if (b"Machine Type: Flashforge Finder" not in self.info
                    or b"Firmware: V1.5 20170419" not in self.info):
                raise ClientError("Unsupported identity/firmware: only observed Finder V1.5 20170419 is enabled")
            return self
        except BaseException:
            await self.close()
            raise

    async def __aexit__(self, exc_type, *_):
        if exc_type is not None and issubclass(exc_type, asyncio.CancelledError):
            self._healthy = False
        await self.close()

    async def _send(self, data, timeout):
        seq = self.record.data("client_to_server", data) if self.record else None
        self.writer.write(data)
        await asyncio.wait_for(self.writer.drain(), timeout)
        if self.record:
            self.record.event("forward_complete", direction="client_to_server", data_seq=seq)

    async def _line(self, deadline):
        while True:
            end = self.buffer.find(b"\r\n")
            if end >= 0:
                if end + 2 > self.config.max_line_size:
                    raise ClientError("Printer reply line exceeds configured limit")
                line = bytes(self.buffer[:end])
                del self.buffer[:end + 2]
                return line
            if len(self.buffer) >= self.config.max_line_size:
                raise ClientError("Printer reply line exceeds configured limit")
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                raise TimeoutError("Printer reply deadline expired")
            chunk = await asyncio.wait_for(self.reader.read(4096), remaining)
            if not chunk:
                if self.record:
                    self.record.event("eof", direction="server_to_client")
                raise ClientError("Printer disconnected before a complete reply")
            if self.record:
                self.record.data("server_to_client", chunk)
            self.buffer.extend(chunk)

    async def _command(self, command, *, timeout=None):
        timeout = timeout or self.config.timeout
        self._healthy = False
        await self._send(("~" + command + "\r\n").encode("ascii"), timeout)
        deadline = asyncio.get_running_loop().time() + timeout
        lines = []
        count = 0
        while True:
            line = await self._line(deadline)
            count += len(line) + 2
            if count > self.config.max_reply_size:
                raise ClientError("Printer reply exceeds configured limit")
            if line.lower().startswith((b"error", b"failed", b"resend")):
                raise ClientError(f"Printer rejected {command.split()[0]}: {line.decode('ascii', 'backslashreplace')}")
            if line == b"ok":
                expected = f"CMD {command.split()[0]} Received.".encode()
                if not lines or lines[0] != expected:
                    raise ClientError("Unexpected command reply; session is not safe to reuse")
                self._healthy = True
                return tuple(lines[1:])
            lines.append(line)

    def _ready_session(self):
        if not self.writer or self.writer.is_closing() or not self._claimed or not self._healthy or not self._command_mode:
            raise ClientError("Session is not ready; close it and reconnect explicitly")

    async def _require_idle(self):
        reply = await self._command("M119")
        if b"MachineStatus: READY" not in reply:
            raise ClientError("Printer is not READY; refusing upload/start without cancelling its current work")

    async def status(self):
        async with self._lock:
            self._ready_session()
            try:
                return {cmd: await self._command(cmd) for cmd in ("M119", "M105", "M27")}
            except BaseException:
                self._healthy = False
                raise

    async def upload(self, filename, *, remote_name=None, progress=None):
        path = validate_file(filename, self.config.max_file_size)
        destination = remote_path(remote_name if remote_name is not None else path.name)
        async with self._lock:
            self._ready_session()
            with path.open("rb") as source:
                before = os.fstat(source.fileno())
                if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= self.config.max_file_size:
                    raise ValueError("Upload source is not a nonempty, size-limited regular file")
                await self._require_idle()
                size = before.st_size
                acknowledged = 0
                digest = hashlib.sha256()
                save_attempted = False
                # Even after a block ACK the peer still expects binary frames,
                # not M602. On ANY upload failure close, don't inject cleanup.
                self._command_mode = False
                try:
                    reply = await self._command(f"M28 {size} {destination}")
                    expected = f"Writing to file: {destination}  Length: {size}".encode()
                    if reply != (expected,):
                        raise ClientError("Unexpected M28 path/length confirmation")
                    index = 0
                    while acknowledged < size:
                        chunk = source.read(min(BLOCK_SIZE, size - acknowledged))
                        if len(chunk) != min(BLOCK_SIZE, size - acknowledged):
                            raise ClientError("Source file was truncated during upload")
                        self._healthy = False
                        await self._send(encode_frame(index, chunk), self.config.timeout)
                        ack = await self._line(asyncio.get_running_loop().time() + self.config.timeout)
                        if ack != f"N{index} ok".encode():
                            raise ClientError(f"Expected block ACK N{index}, received {ack!r}; no retry attempted")
                        self._healthy = True
                        digest.update(chunk)
                        acknowledged += len(chunk)
                        index += 1
                        if progress:
                            progress(acknowledged, size)
                    after = os.fstat(source.fileno())
                    if source.read(1) or (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (after.st_size, after.st_mtime_ns, after.st_ctime_ns):
                        raise ClientError("Source file changed during upload; not committing it")
                    save_attempted = True
                    reply = await self._command("M29", timeout=self.config.save_timeout)
                    if reply != (b"Done saving file.",):
                        raise ClientError("Unexpected final save reply")
                    self._command_mode = True
                    return UploadResult(destination, size, digest.hexdigest())
                except (ClientError, OSError, TimeoutError) as exc:
                    self._healthy = False
                    if save_attempted:
                        raise ResultUnknown("M29 was attempted but save was not confirmed; result UNKNOWN. Do not retry blindly.") from exc
                    raise ClientError(f"Upload interrupted after {acknowledged}/{size} acknowledged bytes; partial data may remain. {exc}") from exc

    async def start(self, name, *, confirm=False):
        if not confirm:
            raise ValueError("Start requires explicit confirmation; it may heat and move the printer")
        destination = remote_path(name)
        async with self._lock:
            self._ready_session()
            await self._require_idle()
            try:
                reply = await self._command(f"M23 {destination}")
                if (len(reply) != 2 or not reply[0].startswith(f"File opened: {destination} Size: ".encode())
                        or not reply[0].removeprefix(f"File opened: {destination} Size: ".encode()).isdigit()
                        or reply[1] != b"File selected"):
                    raise ClientError("Unexpected print-start reply")
            except (ClientError, OSError, TimeoutError) as exc:
                self._healthy = False
                raise ResultUnknown("Start attempted but not confirmed; job state UNKNOWN. Check the physical printer.") from exc

    async def stop(self, *, confirm=False):
        if not confirm:
            raise ValueError("Stop requires explicit confirmation; it cancels current work")
        async with self._lock:
            self._ready_session()
            try:
                reply = await self._command("M26")
                if reply:
                    raise ClientError("Unexpected stop reply")
            except (ClientError, OSError, TimeoutError) as exc:
                self._healthy = False
                raise ResultUnknown("Stop attempted but not confirmed; job state UNKNOWN. Use the physical printer controls.") from exc

    async def close(self):
        if self.writer is None:
            return
        reason = "completed" if self._healthy and self._command_mode else "uncertain_or_interrupted"
        try:
            if self._claimed and self._healthy and self._command_mode:
                try:
                    await self._command("M602")
                except (ClientError, OSError, TimeoutError) as exc:
                    self.cleanup_error = str(exc)
                    LOG.warning("Control release failed; confirmed operations remain confirmed: %s", exc)
                    reason = "release_failed"
        finally:
            self.writer.close()
            try:
                await asyncio.wait_for(self.writer.wait_closed(), self.config.connect_timeout)
            except (ConnectionError, OSError, TimeoutError):
                pass
            self._claimed = False
            self._healthy = False
            if self.record:
                self.record.close(reason)
