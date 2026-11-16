"""Check-runner contracts with stub processes; never recursively run the suite."""

from contextlib import redirect_stderr, redirect_stdout
import io
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

from helpers import workspace_tempdir
from tools import check


class CheckRunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = workspace_tempdir()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "tests").mkdir()
        for name in ("test_z.js", "test_a.js", "helpers.js"):
            (self.root / "tests" / name).write_text("// Never executed by these tests.\n")
        self.output = io.StringIO()
        self.errors = io.StringIO()

    def invoke(self, arguments):
        with (
            patch.object(check, "ROOT", self.root),
            redirect_stdout(self.output),
            redirect_stderr(self.errors),
        ):
            return check.main(arguments)

    def test_plan_uses_same_python_and_discovers_all_node_scripts_in_stable_order(self):
        commands = check.checks(self.root, "/fake/node")
        self.assertEqual(commands[0][1], [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"])
        self.assertEqual([label for label, _ in commands[1:-1]], ["test_a.js", "test_z.js"])
        self.assertEqual(commands[-1][1], [sys.executable, "tools/export_reviewed_traces.py", "--check"])
        (self.root / "tests" / "test_new.js").write_text("// Also never executed.\n")
        self.assertEqual(len(check.checks(self.root, "/fake/node")), 5)
        self.assertEqual(len(check.checks(self.root)), 2)

    def test_full_run_preflights_node_and_passes_project_local_scratch_to_every_process(self):
        results = [subprocess.CompletedProcess([], 0, stdout="v18.20.0\n")]
        results += [subprocess.CompletedProcess([], 0)] * 4
        with (
            patch.object(check.shutil, "which", return_value="/fake/node"),
            patch.object(check.subprocess, "run", side_effect=results) as run,
        ):
            self.assertEqual(self.invoke([]), 0)
        self.assertEqual(run.call_count, 5)
        self.assertEqual(run.call_args_list[0].args[0], ["/fake/node", "--version"])
        for call in run.call_args_list:
            self.assertEqual(call.kwargs["cwd"], self.root)
            self.assertEqual(call.kwargs["env"]["TMPDIR"], str(self.root / ".tmp"))
            self.assertNotEqual(call.kwargs.get("shell"), True)
        self.assertTrue((self.root / ".tmp").is_dir())
        self.assertIn("Python, Node/UI and trace integrity passed", self.output.getvalue())
        self.assertEqual(self.errors.getvalue(), "")

    def test_missing_node_is_a_failure_before_any_python_or_trace_run(self):
        with (
            patch.object(check.shutil, "which", return_value=None),
            patch.object(check.subprocess, "run") as run,
        ):
            self.assertEqual(self.invoke([]), 1)
        run.assert_not_called()
        self.assertIn("--python-only", self.errors.getvalue())
        self.assertNotIn("passed", self.output.getvalue())

    def test_old_or_unknown_node_version_does_not_silently_skip_ui_checks(self):
        for version in ("v16.20.0", "unrecognized"):
            with self.subTest(version=version):
                result = subprocess.CompletedProcess([], 0, stdout=version)
                with (
                    patch.object(check.shutil, "which", return_value="/fake/node"),
                    patch.object(check.subprocess, "run", return_value=result) as run,
                ):
                    self.assertEqual(self.invoke([]), 1)
                self.assertEqual(run.call_count, 1, "only the version probe ran")
        self.assertNotIn("Completed", self.output.getvalue())

    def test_python_only_is_explicit_and_never_looks_up_node(self):
        with (
            patch.object(check.shutil, "which", side_effect=AssertionError("Node lookup forbidden")),
            patch.object(check.subprocess, "run", return_value=subprocess.CompletedProcess([], 0)) as run,
        ):
            self.assertEqual(self.invoke(["--python-only"]), 0)
        self.assertEqual(run.call_count, 2)
        self.assertIn("SKIPPED by explicit --python-only", self.output.getvalue())
        self.assertNotIn("Node/UI and trace integrity passed", self.output.getvalue())

    def test_failure_stops_without_retry_or_success_summary(self):
        results = [subprocess.CompletedProcess([], 0, stdout="v22.0.0")]
        results += [subprocess.CompletedProcess([], 0), subprocess.CompletedProcess([], 7)]
        with (
            patch.object(check.shutil, "which", return_value="/fake/node"),
            patch.object(check.subprocess, "run", side_effect=results) as run,
        ):
            self.assertEqual(self.invoke([]), 7)
        self.assertEqual(run.call_count, 3)
        self.assertIn("FAILED: test_a.js", self.errors.getvalue())
        self.assertNotIn("Completed", self.output.getvalue())

    def test_no_ui_scripts_or_broken_probe_is_not_a_full_pass(self):
        for path in (self.root / "tests").glob("test_*.js"):
            path.unlink()
        with self.assertRaisesRegex(ValueError, "No UI test scripts"):
            check.checks(self.root, "/fake/node")
        error = subprocess.TimeoutExpired(["/fake/node", "--version"], 10)
        with (
            patch.object(check.shutil, "which", return_value="/fake/node"),
            patch.object(check.subprocess, "run", side_effect=error),
        ):
            self.assertEqual(self.invoke([]), 1)
        self.assertNotIn("Completed", self.output.getvalue())

    def test_runner_does_not_modify_parent_environment(self):
        before = dict(os.environ)
        with patch.object(check.subprocess, "run", return_value=subprocess.CompletedProcess([], 0)):
            self.assertEqual(self.invoke(["--python-only"]), 0)
        self.assertEqual(dict(os.environ), before)
