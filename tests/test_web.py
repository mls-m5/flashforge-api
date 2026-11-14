"""Standalone HTTP/UI contracts; ephemeral loopback only, fake Orca, no hardware."""

import asyncio
from dataclasses import replace
import hashlib
import json
import os
import signal
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

from finderlab.client import ClientConfig
from finderlab.simulator import MockConfig, MockPrinter
from finderlab.slicer import SliceConfig
from finderlab.web import MODEL_LIMIT, PRINT_LIMIT, WebConfig, WebServer
from helpers import workspace_tempdir
from test_slicer import FAKE, PAYLOAD


@unittest.skipUnless(os.name == "posix", "Web workspace locking currently requires POSIX")
class WebTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = workspace_tempdir(); self.root = Path(self.temp.name)
        self.mock = await MockPrinter(MockConfig(port=0)).__aenter__()
        self.config = WebConfig(port=0, data_dir=self.root / "web-data", enable_upload=True,
                                client=ClientConfig(port=self.mock.address[1]))
        self.server = await WebServer(self.config).__aenter__()

    async def asyncTearDown(self):
        await self.server.__aexit__(None, None, None)
        await self.mock.__aexit__(None, None, None)
        self.temp.cleanup()

    async def request(self, method, path, body=b"", headers=None, *, early_eof=False):
        base = {"Host": self.server.authority, "Content-Length": str(len(body))}
        if method == "POST":
            base.update({"Content-Type": "application/json", "Origin": "http://" + self.server.authority,
                         "X-Finder-Token": self.server.token})
        base.update(headers or {})
        raw = (f"{method} {path} HTTP/1.1\r\n" + "".join(f"{k}: {v}\r\n" for k, v in base.items()) + "\r\n").encode()
        reader, writer = await asyncio.open_connection(*self.server.address)
        try:
            # Split header CRLF without timing sleeps.
            writer.write(raw[:-1]); await writer.drain()
            writer.write(raw[-1:] + body); await writer.drain()
            if early_eof: writer.write_eof()
            response = await asyncio.wait_for(reader.read(), 4)
        finally:
            writer.close(); await writer.wait_closed()
        head, content = response.split(b"\r\n\r\n", 1)
        status = int(head.split(b" ")[1])
        return status, content

    async def post(self, path, data):
        return await self.request("POST", path, json.dumps(data).encode())

    async def file(self, name, data=b"; synthetic\x00ok\r\n~M29" * 500):
        return await self.request("POST", "/api/file?name=" + name, data,
                                  {"Content-Type": "application/octet-stream"})

    async def finish(self):
        await asyncio.wait_for(asyncio.shield(self.server.work.task), 5)
        return self.server.work.state

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

    async def test_static_config_and_state_do_not_contact_target(self):
        with patch("finderlab.web.FinderClient") as client:
            for path in ("/", "/app.js", "/style.css", "/api/config", "/api/state"):
                code, content = await self.request("GET", path)
                self.assertEqual(code, 200)
                self.assertTrue(content)
            client.assert_not_called()
        code, data = await self.request("GET", "/api/config")
        self.assertEqual(json.loads(data)["token"], self.server.token)
        self.assertEqual(self.mock.files, {})

    async def test_host_origin_token_and_parser_boundaries(self):
        for headers in ({"Host": "evil.invalid"}, {"Origin": "http://evil.invalid"}, {"X-Finder-Token": "wrong"}):
            code, _ = await self.request("POST", "/api/discard", b'{"confirm":true}', headers)
            self.assertEqual(code, 403)
        for headers in ({"Transfer-Encoding": "chunked"}, {"Content-Length": "-1"},
                        {"Content-Length": "9" * 20}, {"host": self.server.authority}, {"Expect": "100-continue"}):
            code, _ = await self.request("POST", "/api/discard", b"{}", headers)
            self.assertIn(code, (400, 411))
        code, _ = await self.post("/api/save", {"confirm": True, "host": "192.0.2.1"})
        self.assertEqual(code, 400)
        code, _ = await self.request("GET", "/../../AGENTS.md")
        self.assertEqual(code, 404)
        code, _ = await self.request("OPTIONS", "/api/state")
        self.assertEqual(code, 405)
        code, _ = await self.request("POST", "/api/save", b"{" * 2049)
        self.assertEqual(code, 413)
        self.assertEqual(self.mock.files, {})

    async def test_upload_requires_explicit_save_and_never_starts(self):
        payload = b"ok\r\n~M29\0" + bytes(range(256)) * 20
        code, _ = await self.file("sample.gx", payload)
        self.assertEqual(code, 200)
        self.assertEqual(self.mock.files, {})
        code, artifact = await self.request("GET", "/api/artifact")
        self.assertEqual((code, artifact), (200, payload))
        code, _ = await self.post("/api/save", {"remote_name": "sample.gx"})
        self.assertEqual(code, 400)
        code, _ = await self.post("/api/save", {"confirm": True, "remote_name": "sample.gx"})
        self.assertEqual(code, 200)
        state = await self.finish()
        self.assertTrue(state["saved"])
        self.assertEqual(state["sha256"], hashlib.sha256(payload).hexdigest())
        self.assertEqual(self.mock.files["sample.gx"], payload)
        self.assertIsNone(self.mock.active_file)
        manifest = json.loads((Path(state["capture"]) / "manifest.json").read_text())
        self.assertTrue(manifest["metadata"]["upload_confirmed"])
        self.assertFalse(manifest["metadata"]["start_requested"])
        self.assertTrue(manifest["complete"])
        raw = (Path(state["capture"]) / "sessions/s0001/client-to-server.bin").read_bytes()
        commands = []
        while raw:
            if raw.startswith(bytes.fromhex("5a5aa5a5")):
                raw = raw[4112:]
            else:
                command, raw = raw.split(b"\r\n", 1)
                commands.append(command.split()[0])
        self.assertEqual(commands, [b"~M601", b"~M115", b"~M119", b"~M28", b"~M29", b"~M602"])
        code, _ = await self.post("/api/save", {"confirm": True, "remote_name": "again.gx"})
        self.assertEqual(code, 409)

    async def test_receive_limits_early_eof_and_single_slot(self):
        for name in ("../escape.gx", "wrong.3mf", "bad%00.gx"):
            code, _ = await self.file(name)
            self.assertEqual(code, 400)
        for name, size in (("big.gx", PRINT_LIMIT+1), ("big.stl", MODEL_LIMIT+1), ("empty.gx", 0)):
            code, _ = await self.request("POST", "/api/file?name=" + name, b"",
                       {"Content-Type": "application/octet-stream", "Content-Length": str(size)})
            self.assertEqual(code, 413)
        code, _ = await self.request("POST", "/api/file?name=partial.gx", b"short",
                   {"Content-Type": "application/octet-stream", "Content-Length": "100"}, early_eof=True)
        self.assertEqual(code, 400)
        self.assertFalse(self.server.work.state["busy"])
        self.assertEqual(self.server.work.state["phase"], "empty")
        self.assertEqual(list(self.server.work.folder.glob("file-*")), [])
        self.assertEqual((await self.file("one.gx"))[0], 200)
        self.assertEqual((await self.file("two.gx"))[0], 409)
        self.assertEqual((await self.post("/api/discard", {"confirm": True}))[0], 200)
        self.assertEqual((await self.file("two.gx"))[0], 200)

    async def test_disabled_upload_and_slicing_have_no_connection(self):
        self.server.work.config = replace(self.config, enable_upload=False)
        await self.file("print.gcode")
        with patch("finderlab.web.FinderClient") as client:
            self.assertEqual((await self.post("/api/save", {"confirm": True, "remote_name": "p.gcode"}))[0], 409)
            await self.post("/api/discard", {"confirm": True})
            await self.file("model.stl", b"solid synthetic\nendsolid synthetic")
            self.assertEqual((await self.post("/api/slice", {"confirm": True}))[0], 409)
            client.assert_not_called()

    async def test_unknown_save_is_locked_against_blind_retry(self):
        await self.file("print.gx")
        with patch("finderlab.web.FinderClient", side_effect=OSError("synthetic lost connection")) as client:
            await self.post("/api/save", {"confirm": True, "remote_name": "p.gx"})
            state = await self.finish()
            self.assertEqual(state["phase"], "unknown")
            self.assertFalse(state["saved"])
            self.assertEqual((await self.post("/api/save", {"confirm": True, "remote_name": "p.gx"}))[0], 409)
            self.assertEqual(client.call_count, 1)

    async def test_recording_failure_closes_without_saving_or_retrying(self):
        await self.file("quota.gx")
        with patch("finderlab.web.CAPTURE_LIMIT", 128):
            await self.post("/api/save", {"confirm": True, "remote_name": "quota.gx"})
            state = await self.finish()
        self.assertFalse(state["saved"])
        self.assertFalse(state["busy"])
        self.assertEqual(state["phase"], "unknown")
        self.assertEqual(self.mock.files, {})
        manifest = json.loads((Path(state["capture"]) / "manifest.json").read_text())
        self.assertFalse(manifest["complete"])
        self.assertEqual((await self.post("/api/save", {"confirm": True, "remote_name": "quota.gx"}))[0], 409)

    async def test_storage_quota_and_workspace_lock(self):
        with patch("finderlab.web.STORAGE_LIMIT", 100):
            self.assertEqual((await self.file("quota.gx"))[0], 507)
        other = WebServer(self.config)
        with self.assertRaises(OSError):
            await other.__aenter__()
        self.assertFalse(self.server.work.state["busy"])

    def configure_fake_orca(self, behavior="ok"):
        fake = self.root / "fake-orca"
        fake.write_text(f"#!{sys.executable}\nBEHAVIOR={behavior!r}\nPAYLOAD={PAYLOAD!r}\n" + FAKE)
        fake.chmod(0o700)
        settings = {
            "machine": {"gcode_flavor": "sailfish", "printable_area": ["0x0", "10x0", "10x10"],
                        "printable_height": "10", "use_relative_e_distances": "0",
                        "machine_start_gcode": "; synthetic", "machine_end_gcode": "; synthetic"},
            "process": {"layer_height": "0.2", "initial_layer_print_height": "0.2", "travel_speed": "10", "travel_speed_z": "1"},
            "filament": {"nozzle_temperature": ["0"], "nozzle_temperature_initial_layer": ["0"]}}
        profiles = {}
        for kind, values in settings.items():
            path = self.root / (kind + ".json")
            path.write_text(json.dumps({"type": kind, **values}))
            profiles[kind] = path
        cfg = SliceConfig(**profiles, orca=str(fake), timeout=3)
        self.server.work.config = replace(self.config, slicing=cfg)

    async def test_fake_slice_then_separate_review_and_save_gate(self):
        self.configure_fake_orca()
        await self.file("model.stl", b"solid synthetic\nendsolid synthetic")
        with patch("finderlab.web.FinderClient") as client:
            self.assertEqual((await self.post("/api/slice", {"confirm": True}))[0], 200)
            state = await self.finish()
            client.assert_not_called()
        self.assertEqual(state["phase"], "review")
        self.assertTrue(state["sliced"])
        self.assertEqual((await self.request("GET", "/api/artifact"))[1], PAYLOAD)
        self.assertEqual((await self.post("/api/save", {"confirm": True, "remote_name": "sliced.gcode"}))[0], 409)
        self.server.work.config = replace(self.server.work.config, allow_sliced_upload=True)
        self.assertEqual((await self.post("/api/save", {"confirm": True, "remote_name": "wrong.gx"}))[0], 400)
        await self.post("/api/save", {"confirm": True, "remote_name": "sliced.gcode"})
        self.assertTrue((await self.finish())["saved"])
        self.assertEqual(self.mock.files["sliced.gcode"], PAYLOAD)
        self.assertIsNone(self.mock.active_file)

    async def test_busy_slot_and_shutdown_cancel_local_work_only(self):
        self.configure_fake_orca()
        await self.file("model.stl", b"solid synthetic\nendsolid synthetic")
        entered = asyncio.Event()
        async def wait_for_shutdown(*args, **kwargs):
            entered.set()
            await asyncio.Event().wait()
        with patch("finderlab.web.slice_model", side_effect=wait_for_shutdown), patch("finderlab.web.FinderClient") as client:
            await self.post("/api/slice", {"confirm": True})
            await asyncio.wait_for(entered.wait(), 2)
            self.assertEqual((await self.post("/api/discard", {"confirm": True}))[0], 409)
            self.assertEqual((await self.file("other.gx"))[0], 409)
            self.assertEqual((await self.post("/api/slice", {"confirm": True}))[0], 409)
            self.assertEqual((await self.post("/api/save", {"confirm": True, "remote_name": "bad.gx"}))[0], 409)
            self.assertEqual((await self.request("GET", "/api/artifact"))[0], 409)
            await self.server.__aexit__(None, None, None)
            client.assert_not_called()
        self.assertFalse(self.server.work.state["busy"])
        self.assertEqual(self.server.work.state["phase"], "failed")
        manifest = json.loads((Path(self.server.work.state["capture"]) / "manifest.json").read_text())
        self.assertTrue(manifest["complete"])
        self.assertEqual(manifest["sessions"], [])

    async def test_failed_fake_slice_never_connects_or_publishes(self):
        self.configure_fake_orca("fail")
        await self.file("model.stl", b"solid synthetic\nendsolid synthetic")
        with patch("finderlab.web.FinderClient") as client:
            await self.post("/api/slice", {"confirm": True})
            state = await self.finish()
            client.assert_not_called()
        self.assertEqual(state["phase"], "failed")
        self.assertFalse(state["artifact"])
        self.assertIn("synthetic Orca error", state["slicer_log"])
        self.assertLessEqual(len(state["slicer_log"]), 4000)
        self.assertEqual((await self.request("GET", "/api/artifact"))[0], 404)
        self.assertEqual(self.mock.files, {})


class WebConfigTests(unittest.TestCase):
    def test_loopback_only_and_fixed_limits(self):
        with self.assertRaises(ValueError): WebConfig(host="0.0.0.0")
        with self.assertRaises(ValueError): WebConfig(client=ClientConfig(max_file_size=100))
