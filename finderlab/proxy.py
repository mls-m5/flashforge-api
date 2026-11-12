"""Byte-preserving recording TCP proxy. No discovery or command injection."""

import asyncio
from dataclasses import dataclass
import ipaddress
import logging
import math

from .capture import Capture, CaptureError

LOG = logging.getLogger(__name__)


@dataclass(frozen=True)
class ProxyConfig:
    target_host: str
    target_port: int = 8899
    host: str = "127.0.0.1"
    port: int = 8899
    idle_timeout: float = 60.0
    connect_timeout: float = 8.0
    max_clients: int = 8

    def __post_init__(self):
        # Requiring an explicit IP also avoids DNS rebinding/proxy-loop ambiguity.
        ipaddress.ip_address(self.target_host)
        if not 0 <= self.port <= 65535 or not 1 <= self.target_port <= 65535:
            raise ValueError("invalid proxy listen/target port")
        if self.max_clients <= 0:
            raise ValueError("max_clients must be positive")
        for value in (self.idle_timeout, self.connect_timeout):
            if not math.isfinite(value) or value <= 0:
                raise ValueError("timeouts must be finite and positive")


class RecordingProxy:
    def __init__(self, config: ProxyConfig, capture: Capture):
        self.config = config
        self.capture = capture
        self._server = None
        self._tasks = set()
        self._writers = set()

    @property
    def address(self):
        host, port, *_ = self._server.sockets[0].getsockname()
        return host, port

    async def start(self):
        if self._server is not None:
            raise RuntimeError("proxy is already running")
        self._server = await asyncio.start_server(
            self._accept, self.config.host, self.config.port, start_serving=False,
        )
        try:
            target = ipaddress.ip_address(self.config.target_host)
            for sock in self._server.sockets:
                host, port, *_ = sock.getsockname()
                bound = ipaddress.ip_address(host)
                local_target = target == bound or (target.is_loopback and bound.is_loopback)
                if port == self.config.target_port and (local_target or (bound.is_unspecified and target.is_loopback)):
                    raise ValueError("proxy target would loop back to its listener")
            await self._server.start_serving()
        except BaseException:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
            raise
        return self

    async def __aenter__(self):
        return await self.start()

    async def __aexit__(self, *_):
        await self.close()

    async def close(self):
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
        for writer in list(self._writers):
            writer.close()
        tasks = list(self._tasks)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    def _accept(self, reader, writer):
        if self.capture.failed or len(self._tasks) >= self.config.max_clients:
            LOG.warning("Rejecting connection: recording failed or client limit reached")
            writer.close()
            return
        self._writers.add(writer)
        task = asyncio.create_task(self._serve(reader, writer))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _serve(self, reader, writer):
        record = None
        upstream = None
        pumps = []
        watchdog = None
        reason = "eof"
        phase = "connect"
        # Shared activity time: a one-way upload should not time out just because
        # the printer has not sent anything in the opposite direction.
        activity = [asyncio.get_running_loop().time()]
        try:
            record = self.capture.session(
                peer=writer.get_extra_info("peername"), local=writer.get_extra_info("sockname"),
                target=[self.config.target_host, self.config.target_port],
            )
            local = writer.get_extra_info("sockname")
            if (ipaddress.ip_address(local[0]) == ipaddress.ip_address(self.config.target_host)
                    and local[1] == self.config.target_port):
                raise ConnectionError("proxy target is its own listener")
            upstream_reader, upstream = await asyncio.wait_for(
                asyncio.open_connection(self.config.target_host, self.config.target_port),
                self.config.connect_timeout,
            )
            self._writers.add(upstream)
            record.event("target_connected", peer=upstream.get_extra_info("peername"))
            phase = "relay"
            activity[0] = asyncio.get_running_loop().time()
            pumps = [
                asyncio.create_task(self._pump(reader, upstream, record, "client_to_server", activity)),
                asyncio.create_task(self._pump(upstream_reader, writer, record, "server_to_client", activity)),
            ]
            watchdog = asyncio.create_task(self._watch_idle(activity))
            # EOF on one pump does not cancel the other; errors/timeouts do.
            relay = asyncio.gather(*pumps)
            try:
                done, _ = await asyncio.wait([relay, watchdog], return_when=asyncio.FIRST_COMPLETED)
                if watchdog in done:
                    await watchdog
                await relay
            finally:
                relay.cancel()
                await asyncio.gather(relay, return_exceptions=True)
        except asyncio.CancelledError:
            reason = "server_shutdown"
            raise
        except CaptureError as exc:
            reason = "capture_failure"
            LOG.error("Recording failed; closing proxy session: %s", exc)
        except (TimeoutError, ConnectionError, OSError) as exc:
            reason = "timeout" if isinstance(exc, TimeoutError) else "connection_error"
            LOG.warning("Proxy %s failed: %s", phase, exc)
            if record and not self.capture.failed:
                try:
                    record.event("error", phase=phase, error_type=type(exc).__name__, message=str(exc))
                except CaptureError as capture_exc:
                    LOG.error("Cannot record proxy error: %s", capture_exc)
        except Exception:
            reason = "internal_error"
            LOG.exception("Unexpected proxy failure")
        finally:
            for task in [*pumps, watchdog]:
                if task:
                    task.cancel()
            await asyncio.gather(*pumps, *([watchdog] if watchdog else []), return_exceptions=True)
            for stream in (upstream, writer):
                if stream:
                    stream.close()
                    try:
                        await stream.wait_closed()
                    except (ConnectionError, OSError):
                        pass
                    self._writers.discard(stream)
            if record:
                try:
                    record.close(reason)
                except CaptureError as exc:
                    LOG.error("Cannot finish proxy recording: %s", exc)

    async def _pump(self, source, destination, record, direction, activity):
        while True:
            data = await source.read(65536)
            if not data:
                record.event("eof", direction=direction)
                if destination.can_write_eof():
                    destination.write_eof()
                    await asyncio.wait_for(destination.drain(), self.config.idle_timeout)
                return
            activity[0] = asyncio.get_running_loop().time()
            seq = record.data(direction, data)
            destination.write(data)
            await asyncio.wait_for(destination.drain(), self.config.idle_timeout)
            activity[0] = asyncio.get_running_loop().time()
            record.event("forward_complete", direction=direction, data_seq=seq)

    async def _watch_idle(self, activity):
        while True:
            remaining = self.config.idle_timeout - (asyncio.get_running_loop().time() - activity[0])
            if remaining <= 0:
                raise TimeoutError("bidirectional connection idle timeout")
            await asyncio.sleep(remaining)
