"""Parallel runner contracts; disposable local modules, not recursive suites."""

from contextlib import redirect_stderr, redirect_stdout
import io
import os
from pathlib import Path
import threading
import unittest
from unittest.mock import patch

from helpers import workspace_tempdir
from tools import test_python as runner


class ParallelCheckTests(unittest.TestCase):
    def setUp(self):
        self.temp = workspace_tempdir()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "tests").mkdir()
        self.output = io.StringIO()
        self.errors = io.StringIO()

    def invoke(self, jobs=2):
        with redirect_stdout(self.output), redirect_stderr(self.errors):
            return runner.run(self.root, jobs)

    def test_real_modules_run_once_in_distinct_processes_with_local_tmpdir(self):
        for letter in "ab":
            (self.root / "tests" / f"test_{letter}.py").write_text(
                "import os, pathlib, unittest\n"
                "class Fixture(unittest.TestCase):\n"
                " def test_identity(self):\n"
                "  root = pathlib.Path(__file__).resolve().parents[1]\n"
                "  self.assertEqual(os.environ['TMPDIR'], str(root / '.tmp'))\n"
                f"  (root / '{letter}.pid').write_text(str(os.getpid()))\n"
            )
        before = dict(os.environ)
        self.assertEqual(self.invoke(), 0)
        pids = {(self.root / f"{letter}.pid").read_text() for letter in "ab"}
        self.assertEqual(len(pids), 2)
        self.assertNotIn(str(os.getpid()), pids)
        self.assertEqual(self.output.getvalue().count("Ran 1 test"), 2)
        self.assertEqual(list((self.root / ".tmp").iterdir()), [])
        self.assertEqual(dict(os.environ), before)

    def test_workers_overlap_logs_remain_grouped_and_every_failure_is_reported(self):
        for letter in "ab":
            (self.root / "tests" / f"test_{letter}.py").write_text("# Stubbed process only.\n")
        barrier = threading.Barrier(2)
        seen = []

        def execute(root, script, log, env):
            seen.append(script.name)
            self.assertEqual(env["TMPDIR"], str(self.root / ".tmp"))
            barrier.wait(timeout=3)  # Cannot complete if jobs accidentally serialize.
            log.write_text("ERROR details for " + script.name + "\n")
            return 7

        with patch.object(runner, "run_file", side_effect=execute):
            self.assertEqual(self.invoke(), 1)
        self.assertCountEqual(seen, ["test_a.py", "test_b.py"])
        for letter in "ab":
            self.assertIn(f"ERROR details for test_{letter}.py", self.output.getvalue())
            self.assertIn(f"test_{letter}.py", self.errors.getvalue())
        self.assertNotIn("passed", self.output.getvalue())
        self.assertEqual(list((self.root / ".tmp").iterdir()), [])

    def test_invalid_workers_empty_suite_or_nested_tests_fail_before_processes(self):
        with patch.object(runner, "run_file") as run:
            for jobs in (0, 9):
                with self.assertRaises(ValueError):
                    self.invoke(jobs)
            with self.assertRaisesRegex(ValueError, "No Python test files"):
                self.invoke()
            (self.root / "tests" / "test_top.py").write_text("# Fixture\n")
            nested = self.root / "tests" / "nested"
            nested.mkdir()
            (nested / "test_deeper.py").write_text("# Never silently omitted\n")
            with self.assertRaisesRegex(ValueError, "Nested Python tests"):
                self.invoke()
            run.assert_not_called()
