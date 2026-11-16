"""Container argv/config contracts; no Docker/Podman/native/hardware execution."""
import importlib.util
from pathlib import Path
import unittest
from finderlab.__main__ import parser
from helpers import workspace_tempdir

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('container_entrypoint',ROOT/'docker/entrypoint.py')
entry=importlib.util.module_from_spec(spec);spec.loader.exec_module(entry)

class ContainerConfigTests(unittest.TestCase):
    def parsed(self,env,**kwargs):
        result=entry.command(env,**kwargs)
        return result,vars(parser().parse_args(result[2:]))

    def test_default_owns_fresh_dummy_without_printer_or_network_exposure(self):
        command,args=self.parsed({})
        self.assertTrue(args['dummy']);self.assertEqual(args['listen_host'],'127.0.0.1')
        for flag in ('--allow-hardware','--target-host','--auto-monitor','--enable-upload','--enable-job-controls'):
            self.assertNotIn(flag,command)
        command,args=self.parsed({'FINDER_MODE':'offline'})
        self.assertFalse(args['dummy']);self.assertFalse(args['enable_upload']);self.assertFalse(args['enable_monitor'])

    def test_explicit_lan_always_selects_existing_password_peer_policy(self):
        command,args=self.parsed({'FINDER_LISTEN_HOST':'192.168.1.50','FINDER_LAN_NETWORK':'192.168.1.0/24'})
        self.assertTrue(args['lan']);self.assertEqual(args['listen_host'],'192.168.1.50')
        for host in ('0.0.0.0','::','203.0.113.1','10.0.0.1','printer.local'):
            with self.assertRaises(ValueError):entry.command({'FINDER_LISTEN_HOST':host})

    def test_proxy_web_requires_explicit_capabilities_and_no_automatic_polling(self):
        command,args=self.parsed({'FINDER_MODE':'proxy'})
        self.assertEqual(args['target_host'],'127.0.0.1');self.assertEqual(args['target_port'],9000)
        self.assertFalse(args['enable_upload']);self.assertFalse(args['auto_monitor']);self.assertFalse(args['enable_job_controls'])
        command,args=self.parsed({'FINDER_MODE':'proxy','FINDER_ENABLE_UPLOAD':'true','FINDER_ENABLE_JOB_CONTROLS':'true','FINDER_ENABLE_MONITOR':'true'})
        self.assertTrue(args['enable_job_controls']);self.assertTrue(args['enable_monitor']);self.assertFalse(args['auto_monitor'])
        with self.assertRaises(ValueError):entry.command({'FINDER_MODE':'proxy','FINDER_AUTO_MONITOR':'true'})
        with self.assertRaises(ValueError):entry.command({'FINDER_MODE':'dummy','FINDER_ENABLE_UPLOAD':'true'})

    def test_bundled_proxy_never_guesses_hardware_or_loopbacks_to_itself(self):
        env={'FINDER_SERVICE':'proxy','FINDER_PRINTER_HOST':'192.168.1.60'}
        with self.assertRaises(ValueError):entry.command({'FINDER_SERVICE':'proxy'})
        with self.assertRaises(ValueError):entry.command(env)
        command,args=self.parsed(env|{'FINDER_ALLOW_HARDWARE':'true'})
        self.assertEqual(args['command'],'proxy');self.assertEqual(args['host'],'127.0.0.1');self.assertEqual(args['port'],9000)
        self.assertEqual(args['target_host'],'192.168.1.60')
        with self.assertRaises(ValueError):entry.command({'FINDER_SERVICE':'proxy','FINDER_PRINTER_HOST':'127.0.0.1','FINDER_PRINTER_PORT':'9000'})

    def test_slicing_uses_only_fixed_trusted_mount_and_requires_executable_and_profiles(self):
        env={'FINDER_ENABLE_SLICING':'true'}
        with workspace_tempdir() as directory:
            folder=Path(directory);orca=folder/'AppRun';profiles=folder/'profiles';profiles.mkdir()
            with self.assertRaises(ValueError):entry.command(env,profile_dir=profiles,orca=orca)
            orca.write_text('#!/bin/sh\nexit99\n');orca.chmod(0o700)
            for kind in ('machine','process','filament'):(profiles/(kind+'.json')).write_text('{}')
            command,args=self.parsed(env,profile_dir=profiles,orca=orca)
            self.assertTrue(args['check_priming']);self.assertEqual(args['orca'],str(orca))
            command,args=self.parsed(env|{'FINDER_MODE':'proxy','FINDER_ENABLE_UPLOAD':'true','FINDER_ALLOW_SLICED_UPLOAD':'true'},profile_dir=profiles,orca=orca)
            self.assertTrue(args['allow_sliced_upload']);self.assertFalse(args['auto_monitor'])
            (profiles/'machine.json').unlink()
            with self.assertRaises(ValueError):entry.command(env,profile_dir=profiles,orca=orca)

    def test_invalid_settings_fail_instead_of_silently_selecting_fallbacks(self):
        for env in ({'FINDER_MODE':'other'},{'FINDER_ENABLE_UPLOAD':'maybe'},{'FINDER_STORAGE_MIB':'9999'},
                    {'FINDER_WEB_PORT':'8000; touch bad'},{'FINDER_SERVICE':'other'},
                    {'FINDER_MODE':'proxy','FINDER_ENABLE_JOB_CONTROLS':'true'},
                    {'FINDER_MODE':'proxy','FINDER_ALLOW_SLICED_UPLOAD':'true'}):
            with self.assertRaises(ValueError):entry.command(env)

    def test_boolean_spellings_and_ascii_integer_bounds_are_explicit(self):
        for value in ("1", "true", "TRUE", " yes ", "on"):
            with self.subTest(boolean=value):
                self.assertTrue(entry.boolean({"FLAG": value}, "FLAG"))
        for value in ("0", "false", "FALSE", " no ", "off", ""):
            with self.subTest(boolean=value):
                self.assertFalse(entry.boolean({"FLAG": value}, "FLAG", True))
        self.assertTrue(entry.boolean({}, "FLAG", True))
        with self.assertRaises(ValueError):
            entry.boolean({"FLAG": "maybe"}, "FLAG")
        self.assertEqual(entry.integer({}, "PORT", 8000, 1, 65535), 8000)
        for value in ("1", "65535"):
            self.assertEqual(entry.integer({"PORT": value}, "PORT", 8000, 1, 65535), int(value))
        for value in ("", "0", "65536", "-1", " 8000 ", "１２", "12345678901"):
            with self.subTest(integer=value), self.assertRaises(ValueError):
                entry.integer({"PORT": value}, "PORT", 8000, 1, 65535)

    def test_extra_container_arguments_fail_before_exec(self):
        from unittest.mock import patch
        with (
            patch.object(entry.sys, "argv", ["entrypoint.py", "--allow-hardware"]),
            patch.object(entry.os, "execv") as execute,
            patch.object(entry.os, "chdir") as change_directory,
        ):
            with self.assertRaisesRegex(SystemExit, "override the entrypoint explicitly"):
                entry.main()
        execute.assert_not_called()
        change_directory.assert_not_called()

    def test_main_executes_only_validated_cli_argv_without_dumping_environment(self):
        from contextlib import redirect_stdout
        import io
        from unittest.mock import patch
        env = {"FINDER_MODE": "offline", "UNRELATED_SECRET": "not-for-console"}
        output = io.StringIO()
        with (
            patch.object(entry.sys, "argv", ["entrypoint.py"]),
            patch.object(entry.os, "environ", env),
            patch.object(entry.os, "execv") as execute,
            patch.object(entry.os, "chdir") as change_directory,
            redirect_stdout(output),
        ):
            entry.main()
        change_directory.assert_called_once_with(ROOT)
        execute.assert_called_once_with(entry.sys.executable, [entry.sys.executable, *entry.command(env)])
        self.assertNotIn("not-for-console", output.getvalue())

    def test_compose_bundles_native_and_reviewed_profiles_but_excludes_private_inputs(self):
        base=(ROOT/'docker-compose.yml').read_text();extra=(ROOT/'compose.slicing.yml').read_text()
        image=(ROOT/'docker/web.Dockerfile').read_text();ignore=(ROOT/'.dockerignore').read_text()
        self.assertIn('target: slicer',base);self.assertIn('profiles: [printer]',base)
        web=base.split('  finder-proxy:')[0]
        self.assertIn('FINDER_ENABLE_SLICING: "true"',web)
        self.assertNotIn('type: bind',web)
        self.assertIn('COPY profiles/finder2 /profiles',image)
        self.assertIn('!profiles/finder2/provenance.json',ignore)
        self.assertIn('${FINDER_PROFILE_DIR:-./profiles/finder2}',extra)
        self.assertIn('${FINDER_MODE:-dummy}',base);self.assertNotIn('ports:',base)
        self.assertIn('target: slicer',extra);self.assertIn('read_only: true',extra);self.assertIn('create_host_path: false',extra)
        self.assertIn('--version 2.3.0',image);self.assertIn('--appimage-extract',image);self.assertIn('USER finder',image)
        self.assertNotIn('COPY . ',image);self.assertNotIn('COPY local-profiles',image)
        self.assertIn('**/.env',ignore);self.assertIn('**/local-profiles/',ignore)
