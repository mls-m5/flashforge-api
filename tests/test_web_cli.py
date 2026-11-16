"""Workbench cli HTTP contracts; owned ephemeral loopback/fake Orca, no hardware."""

import asyncio
import signal
import sys
from web_helpers import WebTestCase


class WebCliTests(WebTestCase):
    async def test_cli_dummy_rejects_external_endpoint_options(self):
        process = await asyncio.create_subprocess_exec(
            sys.executable, "-m", "finderlab", "web", "--dummy", "--target-port", "9000",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        _, error = await asyncio.wait_for(process.communicate(), 5)
        self.assertEqual(process.returncode, 2)
        self.assertIn(b"owns its endpoint", error)

    async def test_cli_starts_disabled_and_shuts_down_cleanly(self):
        for signum in (signal.SIGINT, signal.SIGTERM):
            with self.subTest(signal=signum):
                await self.cli_shutdown(signum)

    async def cli_shutdown(self, signum):
        process = await asyncio.create_subprocess_exec(
            sys.executable, "-m", "finderlab", "web", "--listen-port", "0",
            "--data-dir", str(self.root / "cli-data"),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        try:
            line = await asyncio.wait_for(process.stdout.readline(), 5)
            self.assertTrue(line.startswith(b"Open http://127.0.0.1:"), line)
            process.send_signal(signum)
            _, errors = await asyncio.wait_for(process.communicate(), 5)
            self.assertEqual(process.returncode, 0, errors.decode())
            self.assertNotIn(b"Traceback", errors)
            self.assertEqual(list((self.root / "cli-data").glob("captures/*")), [])
        finally:
            if process.returncode is None:
                process.kill()
                await process.communicate()
