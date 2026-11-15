"""Offline launcher wiring with generated files, never native/hardware actions."""

from contextlib import redirect_stdout
import io
import ipaddress
import os
import struct
import subprocess
import sys
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
        for forbidden in ("--auto-monitor", "--enable-monitor", "--enable-upload", "--enable-job-controls", "--allow-sliced-upload", "--allow-hardware"):
            self.assertNotIn(forbidden, command)
        self.assertEqual(command[command.index("--machine")+1], str(self.profiles / "machine.json"))

    def test_dummy_mode_only_requests_an_owned_endpoint(self):
        command = launcher.build_command(dummy_upload_test=True)
        self.assertIn("--dummy", command)
        for flag in ("--target-host", "--target-port", "--allow-hardware", "--enable-job-controls"):
            self.assertNotIn(flag, command)
        self.assertIn(str(self.root / "web-data/dummy-upload-test"), command)

    def test_isolated_skirt_test_uses_same_default_but_restricts_target_mode(self):
        command = launcher.build_command(native_skirt_test=True)
        self.assertIn('--check-priming',command)
        self.assertEqual(command[command.index('--machine')+1],str(self.profiles/'machine.json'))
        for flag in ('--enable-upload','--enable-job-controls','--allow-sliced-upload'):
            self.assertNotIn(flag,command)
        self.assertIn('--dummy',launcher.build_command(native_skirt_test=True,dummy_upload_test=True))
        with self.assertRaisesRegex(ValueError,'offline/owned-dummy'):
            launcher.build_command(native_skirt_test=True,proxy_port=9000)

    def test_all_standard_modes_use_skirt_and_mandatory_priming_guard(self):
        self.assertEqual(launcher.DEFAULT_PROFILE_NAME,'finder-offline-03')
        for options in ({},{'dummy_upload_test':True},{'proxy_port':9000},
                        {'proxy_port':9000,'enable_job_controls':True,'allow_sliced_upload':True},
                        {'proxy_port':9000,'lan_host':'192.168.1.20','enable_job_controls':True,'allow_sliced_upload':True}):
            with self.subTest(options=options):
                command=launcher.build_command(**options)
                self.assertEqual(command.count('--check-priming'),1)
                for kind in ('machine','process','filament'):
                    self.assertEqual(command[command.index('--'+kind)+1],str(self.profiles/(kind+'.json')))

    def test_missing_skirt_never_falls_back_to_old_fixed_prime_profile(self):
        old=self.root/'local-profiles/finder-offline-02';old.mkdir(parents=True)
        for kind in ('machine','process','filament'):(old/(kind+'.json')).write_text('{}')
        with patch.object(launcher,'PROFILE',self.root/'local-profiles/finder-offline-03'):
            with self.assertRaisesRegex(ValueError,'profile missing/invalid'):
                launcher.build_command(proxy_port=9000)

    def test_proxy_mode_uses_loopback_and_explicit_generated_job_gates(self):
        command = launcher.build_command(proxy_port=9002)
        self.assertIn("--enable-upload", command)
        self.assertEqual(command[command.index("--status-capture")+1], str(self.root / "captures"))
        explicit = launcher.build_command(proxy_port=9002, status_capture=Path("captures/exact-run"))
        self.assertEqual(explicit[explicit.index("--status-capture")+1], str(self.root / "captures/exact-run"))
        self.assertEqual(command[command.index("--target-host")+1], "127.0.0.1")
        self.assertEqual(command[command.index("--target-port")+1], "9002")
        for flag in ("--dummy", "--allow-hardware", "--enable-job-controls", "--allow-sliced-upload"):
            self.assertNotIn(flag, command)
        command = launcher.build_command(proxy_port=9002, enable_job_controls=True, allow_sliced_upload=True)
        self.assertIn("--enable-job-controls", command)
        self.assertIn("--allow-sliced-upload", command)
        for options in ({"proxy_port": 0}, {"proxy_port": 65536},
                        {"proxy_port": 9000, "dummy_upload_test": True},
                        {"enable_job_controls": True}, {"allow_sliced_upload": True}, {"status_capture": Path("captures")}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                launcher.build_command(**options)

    def test_polling_defaults_only_for_proxy_or_owned_dummy_and_opt_out(self):
        self.assertIn("--auto-monitor", launcher.build_command(proxy_port=9000))
        self.assertIn("--auto-monitor", launcher.build_command(dummy_upload_test=True))
        for mode in ({"proxy_port": 9000}, {"dummy_upload_test": True}):
            command = launcher.build_command(**mode, monitor=False)
            self.assertNotIn("--auto-monitor", command)
            self.assertIn("--enable-monitor", command)
        with self.assertRaisesRegex(ValueError, "offline means no printer connection"):
            launcher.build_command(monitor=True)
        with patch("sys.argv", ["start_offline_web.py", "--proxy-port", "9000", "--check"]), \
             patch.object(launcher.os, "execv") as execute, redirect_stdout(io.StringIO()) as output:
            launcher.main()
        execute.assert_not_called()
        self.assertIn("CONNECTS ON STARTUP", output.getvalue())

    def test_lan_sharing_requires_specific_private_interface_and_keeps_action_gates(self):
        command = launcher.build_command(lan_host="192.168.1.20", lan_network="192.168.1.0/24")
        self.assertIn("--lan", command)
        self.assertEqual(command[command.index("--listen-host")+1], "192.168.1.20")
        self.assertEqual(command[command.index("--lan-network")+1], "192.168.1.0/24")
        for flag in ("--enable-upload", "--enable-job-controls", "--allow-sliced-upload", "--auto-monitor"):
            self.assertNotIn(flag, command, "Sharing alone must not enable printer actions")
        full = launcher.build_command(proxy_port=9000, lan_host="192.168.1.20", enable_job_controls=True, allow_sliced_upload=True)
        for flag in ("--enable-upload", "--enable-job-controls", "--allow-sliced-upload", "--auto-monitor", "--lan"):
            self.assertIn(flag, full)
        for options in ({"lan_network": "192.168.1.0/24"}, {"lan_host": "0.0.0.0"}, {"lan_host": "127.0.0.1"},
                        {"lan_host": "203.0.113.2"}, {"lan_host": "192.168.2.20", "lan_network": "192.168.1.0/24"},
                        {"lan_host": "192.168.1.20", "lan_network": "0.0.0.0/0"}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                launcher.build_command(**options)
        with patch("sys.argv", ["start_offline_web.py", "--lan-host", "192.168.1.20", "--check"]), \
             patch.object(launcher.os, "execv") as execute, redirect_stdout(io.StringIO()) as output:
            launcher.main()
        execute.assert_not_called()
        self.assertIn("HTTP is unencrypted", output.getvalue())
        self.assertIn("192.168.1.20", output.getvalue())

    def test_automatic_lan_choice_keeps_proxy_local_and_prints_selected_url(self):
        with patch.object(launcher, "local_ipv4_addresses", return_value={"127.0.0.1", "10.1.2.3", "192.168.1.20"}):
            command = launcher.build_command(proxy_port=9000, lan_host="auto")
            self.assertEqual(command[command.index("--listen-host")+1], "192.168.1.20")
            self.assertEqual(command[command.index("--target-host")+1], "127.0.0.1")
            self.assertEqual(command[command.index("--target-port")+1], "9000")
            self.assertIn("--lan", command)
            with patch("sys.argv", ["start_offline_web.py", "--lan-host", "auto", "--check"]), \
                 patch.object(launcher.os, "execv") as execute, redirect_stdout(io.StringIO()) as output:
                launcher.main()
            execute.assert_not_called()
            self.assertIn("Open http://192.168.1.20:8000", output.getvalue())
            self.assertNotIn("http://auto", output.getvalue())

    def test_auto_selection_does_not_guess_on_missing_or_ambiguous_address(self):
        for addresses in ({"127.0.0.1", "10.1.2.3"}, {"192.168.1.20", "192.168.2.20"}):
            with patch.object(launcher, "local_ipv4_addresses", return_value=addresses), self.assertRaises(ValueError):
                launcher.build_command(lan_host="auto")
        with patch.object(launcher, "local_ipv4_addresses", return_value={"192.168.1.20", "192.168.2.20"}):
            command = launcher.build_command(lan_host="auto", lan_network="192.168.1.0/24")
            self.assertEqual(command[command.index("--listen-host")+1], "192.168.1.20")
        with patch.object(launcher, "local_ipv4_addresses", side_effect=OSError("synthetic permission failure")), \
             self.assertRaisesRegex(ValueError, "Cannot read local interface"):
            launcher.build_command(lan_host="auto")

    def test_default_and_explicit_address_never_enumerate_interfaces(self):
        with patch.object(launcher, "local_ipv4_addresses", side_effect=AssertionError("unexpected enumeration")):
            self.assertNotIn("--lan", launcher.build_command())
            self.assertIn("--lan", launcher.build_command(lan_host="192.168.1.20"))

    @unittest.skipUnless(sys.platform == "linux", "Linux ioctl reader")
    def test_local_interface_reader_uses_only_ioctl_no_connection_or_packets(self):
        names = [(1, "lo"), (2, "eth0"), (3, "down0"), (4, "noipv4")]
        def ioctl(fd, opcode, request):
            name = request.split(b"\x00", 1)[0].decode()
            result = bytearray(256)
            if opcode == 0x8913:
                struct.pack_into("H", result, 16, 0 if name == "down0" else 1)
            else:
                self.assertEqual(opcode, 0x8915)
                self.assertNotEqual(name, "down0", "down interfaces must not be selected")
                if name == "noipv4": raise OSError("no address")
                result[20:24] = ipaddress.IPv4Address("127.0.0.1" if name == "lo" else "192.168.1.20").packed
            return bytes(result)
        with patch.object(launcher.socket, "if_nameindex", return_value=names), \
             patch.object(launcher.socket, "socket") as socket_factory, patch("fcntl.ioctl", side_effect=ioctl):
            self.assertEqual(launcher.local_ipv4_addresses(), {"127.0.0.1", "192.168.1.20"})
            control = socket_factory.return_value.__enter__.return_value
            for method in ("connect", "connect_ex", "send", "sendto", "bind"):
                getattr(control, method).assert_not_called()
            socket_factory.assert_called_once_with(launcher.socket.AF_INET, launcher.socket.SOCK_DGRAM)

    def test_auto_interface_reader_is_bounded_and_does_not_guess_on_other_platforms(self):
        with patch.object(launcher.sys, "platform", "unsupported"), self.assertRaisesRegex(ValueError, "requires Linux"):
            launcher.local_ipv4_addresses()
        with patch.object(launcher.sys, "platform", "linux"), \
             patch.object(launcher.socket, "if_nameindex", return_value=[(1, "lo")] * 257), \
             patch.object(launcher.socket, "socket") as factory, self.assertRaisesRegex(ValueError, "Too many"):
            launcher.local_ipv4_addresses()
        factory.assert_not_called()

    def test_short_lan_wrapper_needs_no_ip_and_keeps_explicit_override(self):
        # Replace python3 with an argv-only stub: never launch a listener/proxy/native slicer.
        stub = self.root / "python3"
        stub.write_text('#!/bin/sh\nprintf "%s\\n" "$@"\n')
        stub.chmod(0o700)
        script = Path(launcher.__file__).resolve().with_name("start_lan_web.sh")
        env = {**os.environ, "PATH": str(self.root) + os.pathsep + os.environ.get("PATH", "")}
        for args, host in (([], "auto"), (["--check"], "auto"), (["192.168.1.20", "--check"], "192.168.1.20")):
            result = subprocess.run(["bash", str(script), *args], env=env, cwd=self.root, capture_output=True, text=True, timeout=5)
            self.assertEqual(result.returncode, 0, result.stderr)
            command = result.stdout.splitlines()
            self.assertEqual(command[command.index("--lan-host")+1], host)
            self.assertEqual(command[command.index("--proxy-port")+1], "9000")
            self.assertIn("--enable-job-controls", command)
            self.assertIn("--allow-sliced-upload", command)

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
             patch.object(launcher, "FALLBACK_ORCA", self.orca), \
             patch.object(launcher, "ARCHIVE_ORCA", self.root / "missing-archive"):
            command = launcher.build_command()
        self.assertEqual(command[command.index("--orca")+1], str(self.orca))
        with self.assertRaises(ValueError):
            launcher.build_command(orca=self.root / "missing-explicit")

    def test_missing_extraction_or_direct_appimage_is_refused(self):
        archive = self.root / "Orca.AppImage"
        archive.write_text("not executed")
        archive.chmod(0o700)
        with patch.object(launcher, "ORCA", self.root / "missing-AppRun"), \
             patch.object(launcher, "ARCHIVE_ORCA", archive):
            with self.assertRaisesRegex(ValueError, "Extracted Orca"):
                launcher.build_command()
        with self.assertRaisesRegex(ValueError, "extracted Orca AppRun"):
            launcher.build_command(orca=archive)

    def test_bounded_storage_override_and_auto_archive_opt_out_are_explicit(self):
        command=launcher.build_command(storage_limit_mib=512,auto_archive=False)
        self.assertEqual(command[command.index('--storage-limit-mib')+1],'512')
        self.assertIn('--no-auto-archive',command)
        defaults=launcher.build_command()
        self.assertNotIn('--storage-limit-mib',defaults);self.assertNotIn('--no-auto-archive',defaults)
        for value in (0,127,2049,True,512.5):
            with self.assertRaises(ValueError):launcher.build_command(storage_limit_mib=value)

    def test_missing_profile_and_invalid_port_are_refused(self):
        for port in (0, 65536):
            with self.assertRaises(ValueError): launcher.build_command(port)
        (self.profiles / "machine.json").unlink()
        with self.assertRaisesRegex(ValueError, "profile missing/invalid"):
            launcher.build_command()
