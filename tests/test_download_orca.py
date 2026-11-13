"""Downloader tests use byte streams, never network access or downloaded executables."""

import hashlib
import io
from pathlib import Path
import unittest
from unittest.mock import patch
import urllib.request

from tools import download_orca as downloader
from helpers import workspace_tempdir


class Opener:
    def __init__(self, data):
        self.data = data
        self.calls = 0

    def open(self, request, **kwargs):
        self.calls += 1
        assert request.full_url.startswith("https://github.com/OrcaSlicer/OrcaSlicer/releases/download/")
        return io.BytesIO(self.data)


class DownloadTests(unittest.TestCase):
    def setUp(self):
        self.temp = workspace_tempdir()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.payload = b"synthetic AppImage test, never execute"
        self.asset = ("synthetic.AppImage", len(self.payload), hashlib.sha256(self.payload).hexdigest())
        self.version = patch.dict(downloader.RELEASES, {"2.3.0": self.asset})
        self.version.start()
        self.addCleanup(self.version.stop)

    def download(self, data=None, **kwargs):
        return downloader.download("2.3.0", root=self.root, opener=Opener(self.payload if data is None else data), **kwargs)

    def assert_clean(self):
        self.assertFalse(list((self.root / ".tmp").glob("orca-download-*")))

    def test_download_verifies_and_reuses_without_network(self):
        opener = Opener(self.payload)
        path = downloader.download("2.3.0", root=self.root, opener=opener)
        self.assertEqual(path.read_bytes(), self.payload)
        self.assertEqual(path.stat().st_mode & 0o777, 0o700)
        self.assertEqual(downloader.download("2.3.0", root=self.root, opener=opener), path)
        self.assertEqual(opener.calls, 1)
        self.assert_clean()

    def test_bad_size_hash_and_failed_download_do_not_publish(self):
        for data in (b"", self.payload[:-1], self.payload + b"x", b"x" * len(self.payload)):
            with self.subTest(data=data), self.assertRaises(ValueError):
                self.download(data)
            self.assertFalse((self.root / ".local-tools" / self.asset[0]).exists())
            self.assert_clean()
        class Broken:
            def open(self, *args, **kwargs):
                raise TimeoutError("synthetic timeout")
        with self.assertRaises(TimeoutError):
            downloader.download("2.3.0", root=self.root, opener=Broken())
        self.assert_clean()

    def test_existing_wrong_file_and_symlink_are_not_overwritten(self):
        parent = self.root / ".local-tools"
        parent.mkdir()
        path = parent / self.asset[0]
        path.write_bytes(b"original")
        with self.assertRaises(ValueError):
            self.download()
        self.assertEqual(path.read_bytes(), b"original")
        path.unlink()
        source = self.root / "original"
        source.write_bytes(self.payload)
        path.symlink_to(source)
        with self.assertRaises(ValueError):
            self.download()
        self.assertTrue(path.is_symlink())
        self.assertEqual(source.read_bytes(), self.payload)

    def test_publication_race_preserves_existing_output(self):
        test = self
        class Racing(Opener):
            def open(self, *args, **kwargs):
                (test.root / ".local-tools" / test.asset[0]).write_bytes(b"concurrent file")
                return super().open(*args, **kwargs)
        with self.assertRaises(FileExistsError):
            downloader.download("2.3.0", root=self.root, opener=Racing(self.payload))
        self.assertEqual((self.root / ".local-tools" / self.asset[0]).read_bytes(), b"concurrent file")
        self.assert_clean()

    def test_timeout_and_redirect_validation(self):
        for timeout in (0, -1, float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                self.download(timeout=timeout)
        with patch.object(downloader.time, "monotonic", side_effect=[0, 2]):
            with self.assertRaises(TimeoutError):
                self.download(timeout=1)
        self.assert_clean()
        with self.assertRaises(ValueError):
            downloader.HTTPSRedirects().redirect_request(
                urllib.request.Request("https://github.com/"), None, 302, "redirect", {}, "http://example.invalid/file")

    def test_auto_version_and_architecture(self):
        with patch.object(downloader.platform, "system", return_value="Linux"), \
                patch.object(downloader.platform, "machine", return_value="x86_64"):
            for libc, expected in (("2.36", "2.3.0"), ("2.38", "2.5.0"), ("2.41", "2.5.0")):
                with patch.object(downloader.platform, "libc_ver", return_value=("glibc", libc)):
                    self.assertEqual(downloader.select_version("auto"), expected)
            self.assertEqual(downloader.select_version("2.3.0"), "2.3.0")
            with patch.object(downloader.platform, "libc_ver", return_value=("musl", "1.2")):
                with self.assertRaises(ValueError):
                    downloader.select_version("auto")
        with patch.object(downloader.platform, "machine", return_value="aarch64"):
            with self.assertRaises(ValueError):
                downloader.select_version("2.5.0")
