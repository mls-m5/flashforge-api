"""Shared test-free workbench fixture; owned ephemeral loopback and fake Orca only."""

import asyncio
from dataclasses import replace
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

from finderlab.client import ClientConfig
from finderlab.simulator import MockConfig, MockPrinter
from finderlab.slicer import SliceConfig
from finderlab.web import WebConfig, WebServer
from helpers import workspace_tempdir
from test_slicer import FAKE, PAYLOAD


async def read_http_response(reader):
    """Read one bounded Content-Length response, not TCP EOF after its body.

    Negative access gates can close with unread request bytes, producing a TCP
    reset after a complete HTTP reply. Resets before a complete frame still fail.
    """
    async with asyncio.timeout(4):
        raw = await reader.readuntil(b"\r\n\r\n")
        if len(raw) > 16384:
            raise ValueError("Oversized test HTTP response headers")
        head = raw[:-4]
        lengths = [line.split(b":", 1)[1].strip() for line in head.split(b"\r\n")[1:]
                   if line.lower().startswith(b"content-length:")]
        if len(lengths) != 1 or not lengths[0].isdigit():
            raise ValueError("Expected exactly one decimal HTTP Content-Length")
        length = int(lengths[0])
        if length > 64 * 1024 * 1024:
            raise ValueError("Oversized test HTTP response body")
        return head, await reader.readexactly(length)


async def close_http_writer(writer):
    """A rejected request may reset TCP during close (notably on Python3.12).

    Ignore only this cleanup error. Request writes, response reads and all
    status/body assertions remain outside this handler and must still fail.
    """
    writer.close()
    try:
        await writer.wait_closed()
    except ConnectionResetError:
        pass


@unittest.skipUnless(os.name == "posix", "Web workspace locking currently requires POSIX")
class WebTestCase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = workspace_tempdir()
        self.root = Path(self.temp.name)
        # Keep the real slicer mutex, but give each fixture its own workspace.
        self.enterContext(patch("finderlab.slicer.ROOT", self.root))
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
        if path == "/api/model":
            base["X-Finder-Token"] = self.server.token
        if getattr(self, "authorization", None):
            base["Authorization"] = self.authorization
        base.update(headers or {})
        raw = (f"{method} {path} HTTP/1.1\r\n" + "".join(f"{k}: {v}\r\n" for k, v in base.items()) + "\r\n").encode()
        reader, writer = await asyncio.open_connection(*self.server.address)
        try:
            # Split header CRLF without timing sleeps.
            writer.write(raw[:-1])
            await writer.drain()
            writer.write(raw[-1:] + body)
            await writer.drain()
            if early_eof:
                writer.write_eof()
            head, content = await read_http_response(reader)
        finally:
            await close_http_writer(writer)
        status = int(head.split(b" ")[1])
        self.last_headers = head
        return status, content

    async def post(self, path, data):
        return await self.request("POST", path, json.dumps(data).encode())

    async def file(self, name, data=b"; synthetic\x00ok\r\n~M29" * 500):
        return await self.request("POST", "/api/file?name=" + name, data,
                                  {"Content-Type": "application/octet-stream"})

    async def finish(self):
        await asyncio.wait_for(asyncio.shield(self.server.work.task), 5)
        return self.server.work.state

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
