"""Persistent verifier/reset contracts; project-local files, no server/printer."""

import base64
import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from finderlab import web_password as passwords
from finderlab.web_access import WebAccess
from helpers import workspace_tempdir

OLD = "correct horse battery staple"
NEW = "a different strong password"


def authorization(password):
    return "Basic " + base64.b64encode(("finder:" + password).encode()).decode()


class PasswordTests(unittest.TestCase):
    def setUp(self):
        self.temp = workspace_tempdir()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / "auth.json"

    def test_salted_pbkdf_verifier_matches_independent_primitive_and_contains_no_plaintext(self):
        first = passwords.make_record(OLD)
        second = passwords.make_record(OLD)
        self.assertNotEqual(first["salt"], second["salt"])
        expected = hashlib.pbkdf2_hmac("sha256", OLD.encode(), bytes.fromhex(first["salt"]), 600000)
        self.assertEqual(first["digest"], expected.hex())
        self.assertTrue(passwords.verify(first, OLD))
        self.assertFalse(passwords.verify(first, NEW))
        passwords.save(self.path, first)
        stored = self.path.read_text()
        self.assertNotIn(OLD, stored)
        self.assertNotIn(authorization(OLD), stored)
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(passwords.load(self.path), first)

    def test_login_survives_restart_without_reprinting_or_regenerating_secret(self):
        first = WebAccess("127.0.0.1", True)
        initial = first.password
        first.initialize_password(self.path)
        before = self.path.read_bytes()
        second = WebAccess("127.0.0.1", True)
        second.initialize_password(self.path)
        self.assertIsNone(second.password)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertTrue(second.authenticated(authorization(initial)))
        self.assertFalse(second.authenticated(authorization(NEW)))

    def test_change_is_persisted_before_memory_switch_and_invalidates_cached_old_login(self):
        access = WebAccess("127.0.0.1", True)
        access.initialize_password(self.path)
        old = access.password
        self.assertTrue(access.authenticated(authorization(old)))
        result = access.change_password({"confirm": True, "current_password": old, "new_password": NEW})
        self.assertTrue(result["password_changed"])
        self.assertFalse(access.authenticated(authorization(old)))
        self.assertTrue(access.authenticated(authorization(NEW)))
        self.assertIsNone(access.password)
        self.assertNotIn(NEW, self.path.read_text())
        restarted = WebAccess("127.0.0.1", True)
        restarted.initialize_password(self.path)
        self.assertTrue(restarted.authenticated(authorization(NEW)))

    def test_failed_atomic_replace_preserves_old_disk_and_memory_credentials(self):
        access = WebAccess("127.0.0.1", True)
        access.initialize_password(self.path)
        old = access.password
        before = self.path.read_bytes()
        with patch("finderlab.web_password.os.replace", side_effect=OSError("disk error")):
            with self.assertRaises(OSError):
                access.change_password({"confirm": True, "current_password": old, "new_password": NEW})
        self.assertEqual(self.path.read_bytes(), before)
        self.assertTrue(access.authenticated(authorization(old)))
        self.assertFalse(access.authenticated(authorization(NEW)))
        self.assertEqual(list(self.root.glob(".auth-*.tmp")), [])

    def test_bounded_single_fingerprint_cache_skips_kdf_only_after_success(self):
        access = WebAccess("127.0.0.1", True)
        login = authorization(access.password)
        original = passwords.verify
        with patch("finderlab.web_password.verify", wraps=original) as verify:
            self.assertTrue(access.authenticated(login))
            self.assertTrue(access.authenticated(login))
            self.assertEqual(verify.call_count, 1)
            self.assertFalse(access.authenticated(authorization(NEW)))
            self.assertEqual(verify.call_count, 2)
        self.assertIsInstance(access._cached, bytes)
        self.assertNotEqual(access._cached, login.encode())
        self.assertEqual(len(access._cached), 32)
        for value in ("Basic " + "a" * 2048, "Basic !!!", "Basic /w==", "Basic " + base64.b64encode(b"other:password123456").decode()):
            self.assertFalse(access.authenticated(value))

    def test_malformed_record_or_link_does_not_silently_reset_password(self):
        self.path.write_text("not JSON")
        self.path.chmod(0o600)
        before = self.path.read_bytes()
        access = WebAccess("127.0.0.1", True)
        with self.assertRaises(ValueError):
            access.initialize_password(self.path)
        self.assertEqual(self.path.read_bytes(), before)
        self.path.unlink()
        target = self.root / "target"
        target.write_text("must not overwrite")
        self.path.symlink_to(target)
        with self.assertRaises(ValueError):
            access.initialize_password(self.path)
        self.assertEqual(target.read_text(), "must not overwrite")

    def test_record_schema_work_factor_and_permissions_are_strict(self):
        record = passwords.make_record(OLD)
        for changed in (record | {"iterations": 1}, record | {"salt": "bad"}, record | {"extra": "secret"}):
            with self.assertRaises(ValueError):
                passwords.validate_record(changed)
        passwords.save(self.path, record)
        self.path.chmod(0o644)
        with self.assertRaises(ValueError):
            passwords.load(self.path)

    def test_new_password_bounds_and_controls_do_not_get_stored(self):
        for invalid in (None, True, "short", "x" * 129, "password with\nnewline", "bad surrogate" + "\ud800"):
            with self.subTest(kind=type(invalid).__name__), self.assertRaises(ValueError):
                passwords.make_record(invalid)
        record = passwords.make_record("en lång: lösenfras med åäö")
        self.assertTrue(passwords.verify(record, "en lång: lösenfras med åäö"))
