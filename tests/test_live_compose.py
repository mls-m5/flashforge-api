"""Live startup contracts and passive readiness; synthetic /proc, no sockets."""

import ast
import importlib.util
import os
from pathlib import Path
import unittest
from unittest.mock import patch

from finderlab.__main__ import parser
from helpers import workspace_tempdir

ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


health = load("proxy_health", ROOT / "docker/proxy_health.py")
entry = load("live_entrypoint", ROOT / "docker/entrypoint.py")


def example_environment():
    lines = (ROOT / ".env.example.live").read_text().splitlines()
    return dict(line.split("=", 1) for line in lines if line and not line.startswith("#"))


class LiveComposeTests(unittest.TestCase):
    def test_live_example_selects_bundled_proxy_full_workflow_and_existing_cli_gates(self):
        env = example_environment()
        self.assertEqual(env["COMPOSE_FILE"], "docker-compose.yml:compose.live.yml")
        self.assertEqual(env["COMPOSE_PROFILES"], "printer")
        self.assertEqual(env["FINDER_MODE"], "proxy")
        self.assertEqual(env["FINDER_PRINTER_HOST"], "", "never publish/guess a printer target")
        with self.assertRaisesRegex(ValueError, "Set FINDER_PRINTER_HOST explicitly"):
            entry.command(env | {"FINDER_SERVICE": "proxy"})
        with workspace_tempdir() as directory:
            folder = Path(directory)
            tool = folder / "AppRun"
            tool.write_text("#!/bin/sh\nexit 99\n")
            tool.chmod(0o700)
            for kind in ("machine", "process", "filament"):
                (folder / (kind + ".json")).write_text("{}")
            args = entry.command(env | {"FINDER_ENABLE_SLICING": "true"}, profile_dir=folder, orca=tool)
            parsed = vars(parser().parse_args(args[2:]))
        for key in ("enable_upload", "enable_job_controls", "allow_sliced_upload", "enable_monitor", "auto_monitor", "check_priming"):
            self.assertTrue(parsed[key], key)
        self.assertFalse(parsed["dummy"])
        self.assertEqual((parsed["target_host"], parsed["target_port"]), ("127.0.0.1", 9000))
        proxy = entry.command(env | {"FINDER_SERVICE": "proxy", "FINDER_PRINTER_HOST": "192.0.2.10"})
        self.assertIn("192.0.2.10", proxy)  # Literal synthetic config, never connected.
        with self.assertRaises(ValueError):
            entry.command(env | {"FINDER_SERVICE": "proxy", "FINDER_PRINTER_HOST": "192.0.2.10", "FINDER_ALLOW_HARDWARE": "false"})

    def test_live_overlay_waits_for_passive_health_without_weakening_default_compose(self):
        overlay = (ROOT / "compose.live.yml").read_text()
        base = (ROOT / "docker-compose.yml").read_text()
        image = (ROOT / "docker/web.Dockerfile").read_text()
        self.assertIn("condition: service_healthy", overlay)
        self.assertIn("finder-proxy:", overlay)
        self.assertIn('test: ["CMD", "python3", "/app/docker/proxy_health.py"]', overlay)
        self.assertIn("FINDER_MODE: proxy", overlay)
        self.assertIn("${FINDER_MODE:-dummy}", base)
        self.assertIn("profiles: [printer]", base)
        self.assertIn("COPY docker/proxy_health.py /app/docker/proxy_health.py", image)
        self.assertIn("!docker/proxy_health.py", (ROOT / ".dockerignore").read_text())
        self.assertIn("!.env.example.live", (ROOT / ".gitignore").read_text())
        self.assertNotIn("curl", overlay)
        self.assertNotIn("nc ", overlay)
        self.assertNotIn("privileged:", overlay)


class ProxyReadinessTests(unittest.TestCase):
    def setUp(self):
        self.temp = workspace_tempdir()
        self.addCleanup(self.temp.cleanup)
        self.proc = Path(self.temp.name) / "proc"
        (self.proc / "net").mkdir(parents=True)
        self.row()
        process = self.proc / "12"
        (process / "fd").mkdir(parents=True)
        (process / "cmdline").write_bytes(b"python3\0-m\0finderlab\0proxy\0--host\0" + b"127.0.0.1\0")
        (process / "fd/3").symlink_to("socket:[1234]")

    def row(self, *, address="0100007F:2328", state="0A", inode="1234"):
        content = ("sl local_address rem_address st tx_queue tr retrnsmt uid timeout inode\n"
                   f"0: {address} 00000000:0000 {state} 00000000:00000000 00:00000000 00000000 1000 0 {inode}\n")
        (self.proc / "net/tcp").write_text(content)

    def test_only_actual_container_proxy_owns_matching_loopback_listener(self):
        self.assertTrue(health.ready(9000, self.proc))
        self.assertFalse(health.ready(9001, self.proc))
        self.row(inode="9999")
        self.assertFalse(health.ready(9000, self.proc), "unrelated host listener is not readiness")

    def test_wrong_process_nonlistening_wildcard_or_missing_listener_fails(self):
        for address, state in (("00000000:2328", "0A"), ("0100007F:2328", "01")):
            self.row(address=address, state=state)
            self.assertFalse(health.ready(9000, self.proc))
        self.row()
        (self.proc / "12/cmdline").write_bytes(b"python3\0-m\0finderlab\0mock\0")
        self.assertFalse(health.ready(9000, self.proc))
        (self.proc / "12/cmdline").unlink()
        self.assertFalse(health.ready(9000, self.proc))

    def test_missing_descriptors_and_non_socket_fds_do_not_pass(self):
        descriptor = self.proc / "12/fd/3"
        descriptor.unlink()
        descriptor.write_bytes(b"not a socket")
        with self.assertRaises(OSError):
            health.ready(9000, self.proc)
        descriptor.unlink()
        self.assertFalse(health.ready(9000, self.proc))

    def test_malformed_large_and_overcrowded_proc_data_fails_boundedly(self):
        (self.proc / "net/tcp").write_text("header\nmalformed\n")
        self.assertFalse(health.ready(9000, self.proc))
        (self.proc / "net/tcp").write_bytes(b"x" * (256 * 1024 + 1))
        with self.assertRaises(ValueError):
            health.ready(9000, self.proc)
        self.row()
        for index in range(1000, 1513):
            (self.proc / str(index)).mkdir()
        self.assertFalse(health.ready(9000, self.proc))

    def test_main_validates_config_and_fails_closed_without_printing_credentials(self):
        for value in ("", "-1", "65536", "１２", "12345678901"):
            with patch.dict(os.environ, {"FINDER_PROXY_PORT": value}), patch.object(health, "ready", return_value=False):
                self.assertEqual(health.main(), 1)
        for error in (OSError("not readable"), ValueError("oversized")):
            with patch.object(health, "ready", side_effect=error):
                self.assertEqual(health.main(), 1)
        with patch.dict(os.environ, {"FINDER_PROXY_PORT": "9000"}), patch.object(health, "ready", return_value=True) as ready:
            self.assertEqual(health.main(), 0)
            ready.assert_called_once_with(9000)

    def test_readiness_has_no_network_subprocess_or_printer_import(self):
        tree = ast.parse((ROOT / "docker/proxy_health.py").read_text())
        modules = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                modules.append(node.module)
        self.assertEqual(set(modules), {"os", "pathlib", "sys"})
