"""Packaging wrapper retains diagnostics and exit status; no real suite run."""

import os
from pathlib import Path
import shutil
import subprocess
import unittest

from helpers import workspace_tempdir


@unittest.skipUnless(shutil.which("bash"), "Bash packaging wrapper")
class PackageLogTests(unittest.TestCase):
    def test_success_and_failure_keep_complete_private_unique_logs(self):
        with workspace_tempdir() as directory:
            root = Path(directory)
            (root / "tools").mkdir()
            shutil.copyfile(Path(__file__).resolve().parents[1] / "tools/package_release.sh",
                            root / "tools/package_release.sh")
            (root / "bin").mkdir()
            stub = root / "bin/python3"
            stub.write_text('#!/usr/bin/env bash\n'
                            'if [[ "$1" == --version ]]; then echo "Python fixture"; exit 0; fi\n'
                            'echo "stdout diagnostic"\n'
                            'echo "stderr traceback details" >&2\n'
                            'exit "$FIXTURE_EXIT"\n')
            stub.chmod(0o700)
            env = {**os.environ, "PATH": str(root / "bin") + os.pathsep + os.environ["PATH"],
                   "TMPDIR": str(root)}
            for code in (7, 0):
                result = subprocess.run(["bash", str(root / "tools/package_release.sh"), "--check"],
                                        cwd=root, env={**env, "FIXTURE_EXIT": str(code)},
                                        capture_output=True, text=True, timeout=10)
                self.assertEqual(result.returncode, code, result.stdout + result.stderr)
                self.assertIn("Full packaging log saved:", result.stdout)
            logs = sorted((root / ".tmp/package-logs").glob("*.log"))
            self.assertEqual(len(logs), 2)
            contents = [log.read_text() for log in logs]
            for log, content in zip(logs, contents):
                self.assertEqual(log.stat().st_mode & 0o777, 0o600)
                self.assertIn("Python fixture", content)
                self.assertIn("stdout diagnostic", content)
                self.assertIn("stderr traceback details", content)
            self.assertTrue(any("Exit status: 7" in content for content in contents))
            self.assertTrue(any("Exit status: 0" in content for content in contents))
