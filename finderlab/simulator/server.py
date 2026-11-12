"""Bounded TCP mock implementing an explicitly hypothetical upload protocol."""

import asyncio
from dataclasses import dataclass
import logging
import math
import re
from types import MappingProxyType
from typing import Mapping

from .profile import PROFILE_ID, STATUS_RESPONSES, response

LOG = logging.getLogger(__name__)
NAME = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}\Z")


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

    def __post_init__(self):
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

    def __init__(self, config: MockConfig | None = None):
        self.config = config or MockConfig()
        self._files: dict[str, bytes] = {}
        self._owner: object | None = None
        self._server: asyncio.Server | None = None
        self._tasks: set[asyncio.Task] = set()
        self._writers: set[asyncio.StreamWriter] = set()

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
        if len(self._tasks) >= self.config.max_clients:
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
        LOG.info("Connected %r (profile=%s)", peer, PROFILE_ID)
        try:
            await session.run()
        except TimeoutError:
            LOG.warning("Idle/write timeout for %r; pending upload discarded", peer)
        except (ConnectionError, OSError) as exc:
            LOG.info("Connection lost %r: %s", peer, exc)
        except Exception:
            LOG.exception("Unexpected mock session failure for %r", peer)
        finally:
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

    async def send(self, data: bytes):
        self.writer.write(data)
        await asyncio.wait_for(self.writer.drain(), self.config.idle_timeout)

    async def error(self, message: str):
        await self.send(f"Error: {message}\r\n".encode("ascii"))

    async def run(self):
        while True:
            if self.remaining:
                chunk = await asyncio.wait_for(
                    self.reader.read(min(self.remaining, 65536)),
                    self.config.idle_timeout,
                )
                if not chunk:
                    LOG.warning("EOF during upload; discarding %r", self.pending_name)
                    return
                self.pending_data.extend(chunk)
                self.remaining -= len(chunk)
                continue
            try:
                line = await asyncio.wait_for(
                    self.reader.readuntil(b"\r\n"), self.config.idle_timeout,
                )
            except asyncio.IncompleteReadError as exc:
                if exc.partial or self.pending_name is not None:
                    LOG.warning("EOF before command/upload completion; discarding pending state")
                return
            except asyncio.LimitOverrunError:
                await self.error("Command too long; connection closing")
                return
            if len(line) > self.config.max_command_size:
                await self.error("Command too long; connection closing")
                return
            try:
                text = line[:-2].decode("ascii")
            except UnicodeDecodeError:
                await self.error("Commands must be ASCII")
                continue
            # repr escapes control bytes; no binary upload content is logged.
            LOG.info("Command %r", text)
            await self.command(text)

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
                await self.send(response(cmd, "Control Success V2.1."))
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
        elif cmd in STATUS_RESPONSES:
            if args:
                await self.error(f"{cmd} takes no arguments")
            else:
                await self.send(response(cmd, STATUS_RESPONSES[cmd]))
        elif cmd == "M20":
            if args:
                await self.error("M20 takes no arguments")
            else:
                # This listing syntax is a mock convention, not Finder evidence.
                lines = ["Begin file list"]
                lines.extend(f"{name} {len(data)}" for name, data in sorted(self.printer._files.items()))
                lines.append("End file list")
                await self.send(response(cmd, "\r\n".join(lines)))
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
                await self.send(response(cmd))
        else:
            LOG.warning("Unsupported command %r", text)
            await self.error("Unsupported command (synthetic profile)")

    async def begin_upload(self, args):
        if len(args) != 2 or not re.fullmatch(r"[0-9]{1,12}", args[0]):
            await self.error("Expected M28 <byte-count> 0:/user/<filename>")
            return
        size = int(args[0])
        path = args[1]
        prefix = "0:/user/"
        name = path.removeprefix(prefix)
        if not path.startswith(prefix) or not NAME.fullmatch(name) or ".." in name:
            await self.error("Invalid virtual filename")
            return
        if not 0 < size <= self.config.max_file_size:
            await self.error("Invalid file size or file too large")
            return
        files = self.printer._files
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
        await self.send(response("M28"))
