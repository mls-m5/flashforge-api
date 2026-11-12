"""Bounded offline printer with captured framing and explicit mock job policies."""

import asyncio
from dataclasses import dataclass
import logging
import math
import re
from types import MappingProxyType
from typing import Mapping

from ..capture import Capture, CaptureError
from ..protocol.upload import FRAME_SIZE, decode_frame
from .profile import DEFAULT_PROFILE, PROFILES, response

LOG = logging.getLogger(__name__)
NAME = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}\Z")


def virtual_name(path):
    name = path.removeprefix("0:/user/")
    if path.startswith("0:/user/") and NAME.fullmatch(name) and ".." not in name:
        return name
    return None


@dataclass(frozen=True)
class MockConfig:
    host: str = "127.0.0.1"
    port: int = 8899
    idle_timeout: float = 30.0
    max_file_size: int = 8 * 1024 * 1024
    storage_limit: int = 32 * 1024 * 1024
    max_files: int = 32
    max_clients: int = 8
    max_command_size: int = 4096
    profile: str = DEFAULT_PROFILE

    def __post_init__(self):
        if self.profile not in PROFILES:
            raise ValueError(f"unknown mock profile: {self.profile}")
        if not 0 <= self.port <= 65535:
            raise ValueError("port must be between 0 and 65535")
        if not math.isfinite(self.idle_timeout) or self.idle_timeout <= 0:
            raise ValueError("idle_timeout must be finite and positive")
        for field in (
            "max_file_size", "storage_limit", "max_files", "max_clients",
            "max_command_size",
        ):
            if getattr(self, field) <= 0:
                raise ValueError(f"{field} must be positive")


class MockPrinter:
    """One virtual device shared by its TCP sessions.

    Only the control owner may upload. Committed files survive reconnects, but
    not process exit. Pending data is discarded on release, disconnect or timeout.
    No remote path is ever opened on the host filesystem.
    """

    def __init__(self, config: MockConfig | None = None, *, capture: Capture | None = None):
        self.config = config or MockConfig()
        self.profile = PROFILES[self.config.profile]
        self.capture = capture
        self._files: dict[str, bytes] = {}
        self._owner: object | None = None
        self._active_file: str | None = None
        self._server: asyncio.Server | None = None
        self._tasks: set[asyncio.Task] = set()
        self._writers: set[asyncio.StreamWriter] = set()

    @property
    def active_file(self) -> str | None:
        """Virtual job only; nothing here executes G-code or connects to a printer."""
        return self._active_file

    @property
    def files(self) -> Mapping[str, bytes]:
        """Read-only live view for tests/embedding; no network file-download API."""
        return MappingProxyType(self._files)

    @property
    def address(self) -> tuple[str, int]:
        if self._server is None:
            raise RuntimeError("mock is not running")
        host, port, *_ = self._server.sockets[0].getsockname()
        return host, port

    async def start(self):
        if self._server is not None:
            raise RuntimeError("mock is already running")
        self._server = await asyncio.start_server(
            self._accept, self.config.host, self.config.port,
            limit=self.config.max_command_size,
        )
        return self

    def _accept(self, reader, writer):
        if (self.capture and self.capture.failed) or len(self._tasks) >= self.config.max_clients:
            LOG.warning("Connection limit reached; rejecting %r", writer.get_extra_info("peername"))
            writer.close()
            return
        self._writers.add(writer)
        task = asyncio.create_task(self._serve(reader, writer))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def close(self):
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
        tasks = list(self._tasks)
        for writer in list(self._writers):
            writer.close()
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    async def __aenter__(self):
        return await self.start()

    async def __aexit__(self, *_):
        await self.close()

    async def _serve(self, reader, writer):
        session = _Session(self, reader, writer)
        peer = writer.get_extra_info("peername")
        LOG.info("Connected %r (profile=%s)", peer, self.profile.id)
        reason = "eof"
        try:
            if self.capture:
                session.capture = self.capture.session(peer=peer, local=writer.get_extra_info("sockname"))
            reason = await session.run()
        except asyncio.CancelledError:
            reason = "server_shutdown"
            raise
        except CaptureError as exc:
            reason = "capture_failure"
            LOG.error("Recording failed; closing %r: %s", peer, exc)
        except TimeoutError:
            reason = "timeout"
            LOG.warning("Idle/write timeout for %r; pending upload discarded", peer)
        except (ConnectionError, OSError) as exc:
            reason = "connection_error"
            LOG.info("Connection lost %r: %s", peer, exc)
        except Exception:
            reason = "internal_error"
            LOG.exception("Unexpected mock session failure for %r", peer)
        finally:
            if session.capture:
                try:
                    if reason != "eof" and not self.capture.failed:
                        session.capture.event("error", phase="session", error_type=reason)
                    session.capture.close(reason)
                except CaptureError as exc:
                    LOG.error("Cannot finish session recording: %s", exc)
            if self._owner is session:
                self._owner = None
            writer.close()
            try:
                await writer.wait_closed()
            except (ConnectionError, OSError):
                pass
            self._writers.discard(writer)
            LOG.info("Disconnected %r", peer)


class _Session:
    def __init__(self, printer, reader, writer):
        self.printer = printer
        self.config = printer.config
        self.reader = reader
        self.writer = writer
        self.pending_name: str | None = None
        self.pending_data = bytearray()
        self.remaining = 0
        self.block_index = 0
        self.capture = None

    async def send(self, data: bytes):
        seq = self.capture.data("server_to_client", data) if self.capture else None
        LOG.info("Reply %r", data)
        self.writer.write(data)
        await asyncio.wait_for(self.writer.drain(), self.config.idle_timeout)
        if self.capture:
            self.capture.event("forward_complete", data_seq=seq, direction="server_to_client")

    async def error(self, message: str):
        await self.send(f"Error: {message}\r\n".encode("ascii"))

    async def run(self):
        # Read before parsing so captures include partial/invalid commands and
        # pipelined bytes, rather than just the lines the parser accepts.
        buffer = bytearray()
        while True:
            if self.remaining and buffer:
                if self.printer.profile.upload_mode == "framed":
                    if len(buffer) >= FRAME_SIZE:
                        frame = bytes(buffer[:FRAME_SIZE])
                        del buffer[:FRAME_SIZE]
                        try:
                            data = decode_frame(frame, self.block_index, self.remaining)
                        except ValueError as exc:
                            await self.error(f"{exc}; connection closing")
                            return "invalid_upload"
                        self.pending_data.extend(data)
                        self.remaining -= len(data)
                        await self.send(f"N{self.block_index} ok\r\n".encode("ascii"))
                        self.block_index += 1
                        continue
                else:
                    count = min(self.remaining, len(buffer))
                    self.pending_data.extend(buffer[:count])
                    del buffer[:count]
                    self.remaining -= count
                    continue
            if not self.remaining:
                end = buffer.find(b"\r\n")
                if (end >= 0 and end + 2 > self.config.max_command_size) or (
                    end < 0 and len(buffer) >= self.config.max_command_size
                ):
                    await self.error("Command too long; connection closing")
                    return "command_too_long"
                if end >= 0:
                    line = bytes(buffer[:end])
                    del buffer[:end + 2]
                    try:
                        text = line.decode("ascii")
                    except UnicodeDecodeError:
                        await self.error("Commands must be ASCII")
                        continue
                    LOG.info("Command %r", text)
                    await self.command(text)
                    continue
            chunk = await asyncio.wait_for(self.reader.read(65536), self.config.idle_timeout)
            if not chunk:
                if self.capture:
                    self.capture.event("eof", direction="client_to_server")
                if buffer or self.pending_name is not None:
                    LOG.warning("EOF before command/upload completion; discarding pending state")
                    return "incomplete_upload" if self.pending_name is not None else "incomplete_command"
                return "eof"
            if self.capture:
                self.capture.data("client_to_server", chunk)
            buffer.extend(chunk)

    async def command(self, text: str):
        if not text.startswith("~"):
            await self.error("Expected ~ command prefix")
            return
        parts = text[1:].split()
        if not parts:
            await self.error("Empty command")
            return
        cmd, args = parts[0], parts[1:]
        if self.pending_name is not None and cmd not in {"M29", "M602"}:
            await self.error("Upload pending; expected M29 or M602")
            return
        if cmd == "M601":
            if args != ["S1"]:
                await self.error("Expected M601 S1")
            elif self.printer._owner not in (None, self):
                await self.error("Control Failed")
            else:
                self.printer._owner = self
                await self.send(response(cmd, self.printer.profile.control_success))
        elif cmd == "M602":
            if args:
                await self.error("M602 takes no arguments")
            elif self.printer._owner not in (None, self):
                await self.error("Control owned by another session")
            else:
                self.printer._owner = None
                self.pending_name = None
                self.pending_data.clear()
                await self.send(response(cmd, "Control Release."))
        elif cmd in self.printer.profile.status_responses:
            if args:
                await self.error(f"{cmd} takes no arguments")
            else:
                await self.send(response(cmd, self.status_body(cmd)))
        elif cmd == "M20":
            if args:
                await self.error("M20 takes no arguments")
            else:
                # This listing syntax is a mock convention, not Finder evidence.
                lines = ["Begin file list"]
                lines.extend(f"{name} {len(data)}" for name, data in sorted(self.printer._files.items()))
                lines.append("End file list")
                await self.send(response(cmd, "\r\n".join(lines)))
        elif cmd in {"M23", "M26"} and self.printer.profile.supports_jobs:
            await self.job_command(cmd, args)
        elif cmd in {"M28", "M29"}:
            if self.printer._owner is not self:
                await self.error("Control required; send M601 S1")
            elif cmd == "M28":
                await self.begin_upload(args)
            elif args:
                await self.error("M29 takes no arguments")
            elif self.pending_name is None:
                await self.error("No upload pending")
            else:
                name = self.pending_name
                self.printer._files[name] = bytes(self.pending_data)
                LOG.info("Committed virtual file %r (%d bytes)", name, len(self.pending_data))
                self.pending_name = None
                self.pending_data.clear()
                body = "Done saving file." if self.printer.profile.upload_mode == "framed" else ""
                await self.send(response(cmd, body))
        else:
            LOG.warning("Unsupported command %r", text)
            await self.error("Unsupported command (mock policy)")

    async def begin_upload(self, args):
        if len(args) != 2 or not re.fullmatch(r"[0-9]{1,12}", args[0]):
            await self.error("Expected M28 <byte-count> 0:/user/<filename>")
            return
        size = int(args[0])
        path = args[1]
        name = virtual_name(path)
        if name is None:
            await self.error("Invalid virtual filename")
            return
        if not 0 < size <= self.config.max_file_size:
            await self.error("Invalid file size or file too large")
            return
        files = self.printer._files
        if self.printer.active_file is not None:
            await self.error("Virtual job active; upload rejected")
            return
        if name not in files and len(files) >= self.config.max_files:
            await self.error("Too many virtual files")
            return
        # Include the old version during replacement: it remains intact until M29.
        if sum(map(len, files.values())) + size > self.config.storage_limit:
            await self.error("Not enough space")
            return
        self.pending_name = name
        self.pending_data.clear()
        self.remaining = size
        self.block_index = 0
        body = f"Writing to file: {path}  Length: {size}" if self.printer.profile.upload_mode == "framed" else ""
        await self.send(response("M28", body))

    def status_body(self, cmd):
        if self.printer.active_file is not None and self.printer.profile.supports_jobs:
            # Captured active-job shapes, not a timed replay or physical model.
            if cmd == "M119":
                return (
                    "Endstop: X-max: 1 Y-max: 1 Z-max: 0\r\n"
                    "Status: S:1 L:0 J:0 F:1\r\n"
                    "MachineStatus: BUILDING_FROM_SD\r\n"
                    "MoveMode: WAIT_ON_TOOL"
                )
            if cmd == "M105":
                return "T0:21 /220 B:0 /0"
            if cmd == "M27":
                # GX execution offsets differ from file bytes; not inferred here.
                size = len(self.printer._files[self.printer.active_file])
                return f"SD printing byte 0/{size}"
        return self.printer.profile.status_responses[cmd]

    async def job_command(self, cmd, args):
        if self.printer._owner is not self:
            await self.error("Control required; send M601 S1")
        elif cmd == "M26":
            if args:
                await self.error("M26 takes no arguments")
                return
            self.printer._active_file = None
            await self.send(response(cmd))
        elif len(args) != 1:
            await self.error("Expected M23 0:/user/<filename>")
        else:
            name = virtual_name(args[0])
            if name not in self.printer._files:
                await self.error("Unknown virtual file")
            elif self.printer.active_file is not None:
                await self.error("Virtual job already active")
            else:
                self.printer._active_file = name
                size = len(self.printer._files[name])
                await self.send(response(cmd, f"File opened: {args[0]} Size: {size}\r\nFile selected"))
