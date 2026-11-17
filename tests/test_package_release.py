"""Source release contracts in fresh local Git fixtures; fake check runner only."""

from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import shutil
import subprocess
import tarfile
import unittest
from unittest.mock import patch

from helpers import workspace_tempdir
from tools import package_release as release


@unittest.skipUnless(shutil.which("git"), "Packaging requires Git")
class PackageReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = workspace_tempdir()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.git("init", "-q")
        for name in release.REQUIRED | {".gitignore"}:
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("synthetic committed source\n")
        (self.root / ".gitignore").write_text("dist/\n.tmp/\n.env\n")
        (self.root / "tools/check.py").write_text("# Fixture checker only, not a recursive real suite.\n")
        self.git("add", ".")
        self.commit()

    def git(self, *args):
        return subprocess.check_output(["git", *args], cwd=self.root, stderr=subprocess.STDOUT).decode().strip()

    def commit(self):
        self.git("-c", "user.name=Release Test", "-c", "user.email=release-test@example.invalid", "commit", "-qm", "fixture")

    def package(self, **options):
        with redirect_stdout(io.StringIO()):
            return release.package(self.root, **options)

    def test_archive_contains_committed_requirements_but_no_untracked_private_data(self):
        for name in (".env", "result.json", "captures/private.bin", "local-profiles/private.json", "web-data/source.stl"):
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"private bytes must not ship")
        destination = self.package()
        metadata = json.loads((destination / "release.json").read_text())
        archive = destination / metadata["archive"]
        files, _ = release.inspect_archive(archive)
        self.assertTrue(release.REQUIRED <= files)
        self.assertNotIn("result.json", files)
        self.assertNotIn(".env", files)
        self.assertFalse(any(name.startswith(("captures/", "web-data/", "local-profiles/")) for name in files))
        self.assertEqual(metadata["commit"], self.git("rev-parse", "HEAD"))
        self.assertFalse(metadata["container_built"])
        self.assertFalse(metadata["hardware_tested"])
        self.assertEqual(metadata["checks"], {"command": None, "result": "not_run"})
        self.assertIn(metadata["sha256"], (destination / "SHA256SUMS").read_text())
        with self.assertRaisesRegex(ValueError, "already exists"):
            self.package()

    def test_same_commit_archive_is_reproducible(self):
        first = self.package()
        name = json.loads((first / "release.json").read_text())["archive"]
        original = (first / name).read_bytes()
        shutil.rmtree(first)  # This test's disposable fixture output only.
        second = self.package()
        self.assertEqual((second / name).read_bytes(), original)

    def test_dirty_or_staged_tracked_changes_require_commit_before_checks(self):
        path = self.root / "docker-compose.yml"
        path.write_text("modified\n")
        with self.assertRaisesRegex(ValueError, "Commit/review tracked changes"):
            self.package()
        self.git("add", "docker-compose.yml")
        with self.assertRaisesRegex(ValueError, "Commit/review tracked changes"):
            self.package()
        self.assertFalse((self.root / "dist").exists())

    def test_tracked_private_path_missing_requirement_and_failed_checks_do_not_publish(self):
        path = self.root / "captures/private.bin"
        path.parent.mkdir()
        path.write_bytes(b"never archive even if accidentally committed")
        self.git("add", "captures/private.bin")
        self.commit()
        with self.assertRaisesRegex(ValueError, "private/unsafe"):
            self.package()
        self.assertFalse((self.root / "dist").exists())

    def test_failed_check_runner_leaves_no_archive(self):
        (self.root / "tools/check.py").write_text("raise SystemExit(7)\n")
        self.git("add", "tools/check.py")
        self.commit()
        with self.assertRaises(subprocess.CalledProcessError):
            self.package(check=True)
        self.assertFalse((self.root / "dist").exists())

    def test_quick_package_does_not_execute_even_a_failing_check_script(self):
        (self.root / "tools/check.py").write_text("raise SystemExit(7)\n")
        self.git("add", "tools/check.py")
        self.commit()
        self.assertTrue(self.package().is_dir())

    def test_explicit_checked_package_forwards_jobs_and_records_actual_validation(self):
        with patch.object(release.subprocess, "run", wraps=subprocess.run) as run:
            destination = self.package(check=True, jobs=4)
        self.assertTrue(any(call.args[0][-3:] == ["tools/check.py", "--jobs", "4"]
                            for call in run.call_args_list))
        metadata = json.loads((destination / "release.json").read_text())
        self.assertEqual(metadata["checks"], {"command": "python3 tools/check.py --jobs 4", "result": "passed"})

    def test_jobs_requires_check_and_is_bounded_before_publication(self):
        for options in ({"jobs": 2}, {"check": True, "jobs": 0}, {"check": True, "jobs": 9}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                self.package(**options)
        self.assertFalse((self.root / "dist").exists())

    def test_missing_required_file_fails_archive_review_before_publication(self):
        self.git("rm", "compose.live.yml")
        self.commit()
        with self.assertRaisesRegex(ValueError, "missing required"):
            self.package()
        self.assertFalse(list((self.root / "dist").rglob("*.tar.gz")))

    def test_path_policy_and_archive_links_are_rejected(self):
        for name in ("/absolute", "../escape", ".git/config", ".env", "nested/.env.local", "dist/old.tar.gz", "result.json", "auth.json", "nested/auth.json", "nested/.auth-secret.tmp"):
            self.assertFalse(release.public_path(name), name)
        for name in (".env.example", ".env.example.live", "profiles/finder2/process.json", "docs/CAPTURES.md"):
            self.assertTrue(release.public_path(name), name)
        archive = self.root / "linked.tar.gz"
        with tarfile.open(archive, "w:gz") as output:
            link = tarfile.TarInfo("finderlab/link")
            link.type = tarfile.SYMTYPE
            link.linkname = "../../escape"
            output.addfile(link)
        with self.assertRaisesRegex(ValueError, "not links/devices"):
            release.inspect_archive(archive)

    def test_source_byte_preflight_rejects_before_running_checks(self):
        with patch.object(release, "MAX_SOURCE_BYTES", 1):
            with self.assertRaisesRegex(ValueError, "Tracked source bytes"):
                self.package()
        self.assertFalse((self.root / ".tmp").exists())
