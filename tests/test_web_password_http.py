"""Persistent LAN login/change over owned ephemeral loopback, never hardware."""

import asyncio
import base64
from dataclasses import replace
import json
import sys
import threading
from unittest.mock import patch

from finderlab.web import WebServer
from web_helpers import WebTestCase

NEW = "new private shared passphrase"


def basic(password):
    return "Basic " + base64.b64encode(("finder:" + password).encode()).decode()


class PasswordHttpTests(WebTestCase):
    async def lan(self):
        await self.server.__aexit__(None, None, None)
        self.server = await WebServer(replace(self.config, lan=True)).__aenter__()
        self.password = self.server.access.password
        self.authorization = basic(self.password)

    async def test_authenticated_change_and_restart_preserve_login_not_plaintext(self):
        await self.lan()
        await self.file("keep.gcode")
        before = dict(self.server.work.state)
        data = {"confirm": True, "current_password": self.password, "new_password": NEW}
        with patch("finderlab.web.FinderClient") as client:
            status, body = await self.post("/api/password", data)
            self.assertEqual(status, 200, body)
            self.assertTrue(json.loads(body)["password_changed"])
            client.assert_not_called()
        self.assertEqual(self.server.work.state, before)
        self.assertEqual((await self.request("GET", "/api/state"))[0], 401)
        self.authorization = basic(NEW)
        self.assertEqual((await self.request("GET", "/api/state"))[0], 200)
        raw = (self.server.work.folder / "auth.json").read_text()
        self.assertNotIn(NEW, raw)
        self.assertNotIn(self.password, raw)
        self.assertNotIn(basic(NEW), raw)
        self.assertEqual(list(self.server.work.folder.glob("captures/*")), [])
        config = self.server.config
        await self.server.__aexit__(None, None, None)
        self.server = await WebServer(config).__aenter__()
        self.assertIsNone(self.server.access.password)
        status, body = await self.request("GET", "/api/config")
        self.assertEqual(status, 200)
        self.assertTrue(json.loads(body)["password_change_enabled"])
        self.assertNotIn(NEW.encode(), body)
        self.assertNotIn(b"salt", body)
        self.assertNotIn(b"digest", body)

    async def test_password_route_is_auth_origin_token_typed_current_password_and_busy_guarded(self):
        await self.lan()
        data = {"confirm": True, "current_password": self.password, "new_password": NEW}
        before = (self.server.work.folder / "auth.json").read_bytes()
        for headers, status in (({"Authorization": ""}, 401), ({"Origin": "http://wrong"}, 403),
                                ({"X-Finder-Token": "wrong"}, 403)):
            code, _ = await self.request("POST", "/api/password", json.dumps(data).encode(), headers)
            self.assertEqual(code, status)
        for changed, status in ((data | {"confirm": False}, 400), (data | {"current_password": "wrong"}, 403),
                                (data | {"new_password": "short"}, 400), (data | {"path": "elsewhere"}, 400)):
            self.assertEqual((await self.post("/api/password", changed))[0], status)
        self.server.work.state["busy"] = True
        try:
            self.assertEqual((await self.post("/api/password", data))[0], 409)
        finally:
            self.server.work.state["busy"] = False
        self.assertEqual((self.server.work.folder / "auth.json").read_bytes(), before)
        self.assertEqual((await self.request("GET", "/password.js", headers={"Authorization": ""}))[0], 401)
        self.assertEqual((await self.request("GET", "/password.js"))[0], 200)

    async def test_loopback_mode_does_not_create_auth_file_or_enable_password_mutation(self):
        status, body = await self.request("GET", "/api/config")
        self.assertEqual(status, 200)
        self.assertFalse(json.loads(body)["password_change_enabled"])
        self.assertFalse((self.server.work.folder / "auth.json").exists())
        self.assertEqual((await self.post("/api/password", {"confirm": True}))[0], 409)

    async def test_offline_reset_refuses_active_workspace_then_changes_only_login(self):
        await self.lan()
        folder = self.server.work.folder
        command = [sys.executable, "-m", "finderlab.web_password", "--data-dir", str(folder)]
        process = await asyncio.create_subprocess_exec(
            *command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        output, error = await asyncio.wait_for(process.communicate(), 5)
        self.assertEqual(process.returncode, 1)
        self.assertNotIn(b"Login password", output)
        self.assertIn(b"stop finder-web first", error)
        config = self.server.config
        await self.server.__aexit__(None, None, None)
        process = await asyncio.create_subprocess_exec(
            *command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        output, error = await asyncio.wait_for(process.communicate(), 5)
        self.assertEqual(process.returncode, 0, error)
        reset = output.decode().split("Login password (reset; share privately): ")[1].strip()
        self.server = await WebServer(config).__aenter__()
        self.authorization = basic(reset)
        self.assertEqual((await self.request("GET", "/api/state"))[0], 200)
        self.authorization = basic(self.password)
        self.assertEqual((await self.request("GET", "/api/state"))[0], 401)
        self.assertEqual(list(folder.glob("captures/*")), [])

    async def test_cancelled_password_worker_is_joined_before_unlocking_or_clearing_busy(self):
        entered, release, finished = threading.Event(), threading.Event(), threading.Event()
        def worker(_):
            entered.set()
            release.wait(3)
            finished.set()
            return {"password_changed": True}
        with patch.object(self.server.access, "change_password", side_effect=worker):
            task = asyncio.create_task(self.server.change_password({}))
            try:
                self.assertTrue(await asyncio.to_thread(entered.wait, 2))
                self.assertTrue(self.server.work.state["busy"])
                self.assertTrue(self.server.access_lock.locked())
                task.cancel()
                release.set()
                with self.assertRaises(asyncio.CancelledError):
                    await task
                self.assertTrue(finished.is_set())
                self.assertFalse(self.server.access_lock.locked())
                self.assertFalse(self.server.work.state["busy"])
            finally:
                release.set()
                await asyncio.gather(task, return_exceptions=True)

    async def test_save_failure_keeps_current_login_and_verifier_on_disk(self):
        await self.lan()
        before = (self.server.work.folder / "auth.json").read_bytes()
        with patch("finderlab.web_password.os.replace", side_effect=OSError("disk failed")):
            status, body = await self.post("/api/password", {
                "confirm": True, "current_password": self.password, "new_password": NEW,
            })
        self.assertEqual(status, 500)
        self.assertNotIn(NEW.encode(), body)
        self.assertEqual((self.server.work.folder / "auth.json").read_bytes(), before)
        self.assertEqual((await self.request("GET", "/api/config"))[0], 200)
