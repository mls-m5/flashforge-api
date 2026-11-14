"""Opt-in active status with fresh owned loopback dummies only."""

import asyncio
import json
from pathlib import Path
import unittest
from unittest.mock import AsyncMock, patch

from finderlab.active_status import ActiveMonitor
from finderlab.client import ClientConfig
from finderlab.simulator import MockConfig, MockPrinter
from helpers import workspace_tempdir


async def wait_until(predicate, timeout=3):
    async with asyncio.timeout(timeout):
        while not predicate():
            await asyncio.sleep(0)  # Scheduler yield, not a protocol timing workaround.


class ActiveStatusTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = workspace_tempdir(); self.root = Path(self.temp.name)
        self.dummy = await MockPrinter(MockConfig(port=0)).__aenter__()
        self.monitor = ActiveMonitor(ClientConfig(port=self.dummy.address[1]), self.root, asyncio.Lock(),
                                     lambda: False, interval=0.01, emulated=True)

    async def asyncTearDown(self):
        await self.monitor.close()
        await self.dummy.__aexit__(None, None, None)
        self.temp.cleanup()

    async def test_no_implicit_start_queries_then_explicit_stop_and_no_job_commands(self):
        self.assertIsNone(self.monitor.task)
        self.assertIsNone(self.monitor.capture)
        self.monitor.start()
        await wait_until(lambda: bool(self.monitor.samples))
        capture = self.monitor.capture
        self.assertFalse(self.monitor.report()["passive"])
        self.assertTrue(self.monitor.report()["monitor_running"])
        self.monitor.request_stop()
        await self.monitor.close()
        self.assertFalse(self.monitor.report()["monitor_running"])
        self.assertTrue(self.monitor.report()["stale"])
        manifest = json.loads((capture.path / "manifest.json").read_text())
        self.assertTrue(manifest["complete"])
        self.assertEqual(manifest["metadata"]["operation"], "monitor")
        self.assertFalse(manifest["metadata"]["start_requested"])
        self.assertEqual(len(manifest["sessions"]), 1)
        commands = (capture.path / "sessions/s0001/client-to-server.bin").read_bytes().splitlines()
        self.assertEqual(commands[:2], [b"~M601 S1", b"~M115"])
        self.assertIn(b"~M105", commands)
        self.assertTrue(all(c.split()[0] in (b"~M601", b"~M115", b"~M119", b"~M105", b"~M27", b"~M602") for c in commands))
        before = len(commands)
        await asyncio.sleep(.03)  # Verify explicit stop does not resume periodic activity.
        self.assertEqual(len((capture.path / "sessions/s0001/client-to-server.bin").read_bytes().splitlines()), before)

    async def test_failure_stops_without_automatic_retry(self):
        with patch("finderlab.active_status.FinderClient.status", new=AsyncMock(side_effect=OSError("synthetic lost reply"))) as query:
            self.monitor.start()
            await asyncio.wait_for(self.monitor.task, 3)
            self.assertFalse(self.monitor.enabled)
            self.assertEqual(query.await_count, 1)
            self.assertIn("lost reply", self.monitor.report()["message"])
            await asyncio.sleep(.03)
            self.assertEqual(query.await_count, 1)

    async def test_immediate_stop_before_task_scheduling_finalizes_capture(self):
        self.monitor.start()
        self.monitor.request_stop()
        await self.monitor.close()
        self.assertTrue(self.monitor.capture.closed)
        self.assertEqual(self.monitor.capture.sessions, [])

    async def test_recording_limit_stops_before_any_status_commands(self):
        self.monitor.max_bytes = 128
        self.monitor.start()
        await asyncio.wait_for(self.monitor.task, 3)
        self.assertFalse(self.monitor.enabled)
        self.assertTrue(self.monitor.capture.failed)
        self.assertTrue(self.monitor.report()["stale"])

    async def test_busy_operation_prevents_claim_and_yield_closes_existing_session(self):
        busy = True
        self.monitor.busy = lambda: busy
        self.monitor.start()
        await wait_until(lambda: self.monitor.paused)
        self.assertIsNone(self.monitor.client)
        busy = False
        await wait_until(lambda: bool(self.monitor.samples))
        async with self.monitor.lock:
            await self.monitor.release_client()
            self.assertIsNone(self.monitor.client)
        await self.monitor.close()
