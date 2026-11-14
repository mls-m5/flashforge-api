"""Explicitly started, single-owner status polling. No motion/heat/job commands."""

import asyncio
from dataclasses import asdict
from datetime import datetime, timezone

from .capture import Capture
from .client import FinderClient
from .status_values import decode_status_body


class ActiveMonitor:
    def __init__(self, config, folder, lock, busy, *, emulated=False, interval=1.0, max_bytes=64*1024*1024):
        self.config, self.folder, self.lock, self.busy = config, folder, lock, busy
        self.emulated, self.interval, self.max_bytes = emulated, interval, max_bytes
        self.task = self.client = self.capture = None
        self.enabled = False
        self.samples = {}
        self.sample_session = ""
        self.error = ""
        self.paused = False
        self.started = False

    def start(self):
        if self.task is not None and not self.task.done():
            raise ValueError("Status monitor is already running or stopping")
        self.capture = Capture(self.folder / "captures", "client", max_bytes=self.max_bytes, max_sessions=256,
                               metadata={"operation": "monitor", "interface": "standalone-web", "config": asdict(self.config), "start_requested": False,
                                         "target_kind": "owned_dummy" if self.emulated else "configured_endpoint",
                                         "interval_seconds": self.interval})
        self.enabled = True
        self.error = ""
        self.samples = {}
        self.started = False
        self.task = asyncio.create_task(self.run())

    def request_stop(self):
        was_enabled, self.enabled = self.enabled, False
        if was_enabled and self.started and self.task is not None and not self.task.done():
            self.task.cancel()

    async def release_client(self):
        """Caller holds the shared network lock; yield control before any job."""
        client, self.client = self.client, None
        if client is not None:
            try:
                await client.close()
                if client.cleanup_error:
                    raise OSError("Monitor control release failed: " + client.cleanup_error)
            except Exception as exc:
                self.error = str(exc) or type(exc).__name__
                self.enabled = False
                raise

    async def run(self):
        self.started = True
        try:
            while self.enabled:
                async with self.lock:
                    if not self.enabled:
                        break
                    self.paused = self.busy()
                    if self.paused:
                        await self.release_client()
                    else:
                        if self.client is None:
                            self.client = FinderClient(self.config, capture=self.capture)
                            await self.client.__aenter__()
                            self.capture.manifest.update(model="Flashforge Finder (emulated)" if self.emulated else "Flashforge Finder",
                                                         firmware="V1.5 20170419")
                        replies = await self.client.status()
                        values = {code: decode_status_body(code, b"\r\n".join(lines)) for code, lines in replies.items()}
                        if any(v is None for v in values.values()):
                            raise ValueError("Unrecognized status reply; monitor stopped without retry")
                        stamp = datetime.now(timezone.utc).isoformat()
                        self.client.record.event("status_snapshot", values=values, batch_completed_utc=stamp)
                        self.sample_session = self.client.record.id
                        self.samples = {code: {"values": value, "observed_utc": stamp} for code, value in values.items()}
                # One second AFTER the previous batch; never overlapping requests.
                await asyncio.sleep(self.interval)
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            self.error = str(exc) or type(exc).__name__
            if not self.capture.failed:
                try:
                    self.capture.event("error", phase="monitor", error_type=type(exc).__name__, message=self.error)
                except OSError:
                    pass
        finally:
            self.enabled = False
            try:
                async with self.lock:
                    await self.release_client()
            except Exception as exc:
                self.error = self.error or (str(exc) or type(exc).__name__)
            try:
                self.capture.close()
                if self.capture.failed:
                    self.error = self.error or "Status recording incomplete; monitor stopped"
            except Exception as exc:
                self.error = self.error or (str(exc) or type(exc).__name__)

    async def close(self):
        self.request_stop()
        if self.task is not None:
            await asyncio.gather(self.task, return_exceptions=True)

    def report(self):
        self.paused = self.enabled and self.busy()
        now = datetime.now(timezone.utc)
        samples = {}
        for code, sample in self.samples.items():
            age = (now - datetime.fromisoformat(sample["observed_utc"])).total_seconds()
            samples[code] = {**sample, "age_seconds": round(max(0, age), 1),
                             "stale": age < -5 or age > 10 or not self.enabled}
        return {"enabled": True, "passive": False, "monitor_running": self.enabled,
                "monitor_stopping": self.task is not None and not self.task.done() and not self.enabled,
                "source": self.capture.path.name if self.capture else "", "session": self.sample_session or "awaiting first status batch",
                "upstream": f"{self.config.host}:{self.config.port}", "capture_finalized": bool(self.capture and self.capture.closed),
                "samples": samples, "stale": not self.enabled or not samples or any(s["stale"] for s in samples.values()),
                "message": self.error or ("Active status polling paused for local operation." if self.paused and self.enabled else
                    "Active status polling; timestamp is completion of the status batch, not physical-state validation." if self.enabled else
                    "Active status polling stopped. No automatic reconnect or retry; cached samples are stale.")}
