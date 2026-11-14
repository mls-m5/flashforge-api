"""Offline launcher wiring with generated files, never native/hardware actions."""

from contextlib import redirect_stdout
import io
from pathlib import Path
import unittest
from unittest.mock import patch

from helpers import workspace_tempdir
from tools import start_offline_web as launcher


class LauncherTests(unittest.TestCase):
    def setUp(self):
        self.temp = workspace_tempdir()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.orca = self.root / "fake-orca"
        self.orca.write_text("#!/bin/sh\nexit 99\n")
        self.orca.chmod(0o700)
        self.profiles = self.root / "profiles"
        self.profiles.mkdir()
        for kind in ("machine", "process", "filament"):
            (self.profiles / (kind + ".json")).write_text('{"type":"' + kind + '"}')
        for name, value in (("ROOT", self.root), ("ORCA", self.orca), ("PROFILE", self.profiles)):
            p = patch.object(launcher, name, value)
            p.start(); self.addCleanup(p.stop)

    def test_command_uses_fixed_local_profiles_and_no_printer_enables(self):
        command = launcher.build_command(8001)
        self.assertEqual(command[1:4], ["-m", "finderlab", "web"])
        self.assertEqual(command[command.index("--listen-host")+1], "127.0.0.1")
        self.assertEqual(command[command.index("--listen-port")+1], "8001")
        for forbidden in ("--enable-upload", "--enable-job-controls", "--allow-sliced-upload", "--allow-hardware"):
            self.assertNotIn(forbidden, command)
        self.assertEqual(command[command.index("--machine")+1], str(self.profiles / "machine.json"))

    def test_check_does_not_launch_or_change_directory(self):
        with patch("sys.argv", ["start_offline_web.py", "--check"]), \
             patch.object(launcher.os, "execv") as execute, patch.object(launcher.os, "chdir") as chdir, \
             redirect_stdout(io.StringIO()) as output:
            launcher.main()
        execute.assert_not_called(); chdir.assert_not_called()
        self.assertIn("printer uploads, Start and Cancel are disabled", output.getvalue())

    def test_explicit_executable_and_old_launcher_fallback(self):
        override = self.root / "host-orca"
        override.write_text("#!/bin/sh\nexit 98\n")
        override.chmod(0o700)
        command = launcher.build_command(orca=Path("host-orca"))
        self.assertEqual(command[command.index("--orca")+1], str(override))
        with patch.object(launcher, "ORCA", self.root / "missing-new-appimage"), \
             patch.object(launcher, "FALLBACK_ORCA", self.orca):
            command = launcher.build_command()
        self.assertEqual(command[command.index("--orca")+1], str(self.orca))
        with self.assertRaises(ValueError):
            launcher.build_command(orca=self.root / "missing-explicit")

    def test_missing_profile_and_invalid_port_are_refused(self):
        for port in (0, 65536):
            with self.assertRaises(ValueError): launcher.build_command(port)
        (self.profiles / "machine.json").unlink()
        with self.assertRaisesRegex(ValueError, "profile missing/invalid"):
            launcher.build_command()
