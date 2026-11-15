"""The deployable Finder2 settings must not depend on ignored host state."""
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import unittest

from finderlab.slicer import _check_profile

ROOT = Path(__file__).resolve().parents[1]
PROFILES = ROOT / "profiles" / "finder2"


class BundledProfileTests(unittest.TestCase):
    def test_runtime_profile_identity_and_validation(self):
        manifest = json.loads((PROFILES / "provenance.json").read_text())
        self.assertFalse(manifest["packaging_changed_runtime_bytes"])
        self.assertFalse(manifest["toolpaths_safety_validated"])
        for kind in ("machine", "process", "filament"):
            path = PROFILES / (kind + ".json")
            _check_profile(path, kind)
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),
                             manifest["runtime_sha256"][path.name])
        machine = json.loads((PROFILES / "machine.json").read_text())
        process = json.loads((PROFILES / "process.json").read_text())
        filament = json.loads((PROFILES / "filament.json").read_text())
        self.assertEqual(machine["retraction_length"], ["1.3"])
        self.assertEqual(machine["machine_max_speed_z"], ["7", "7"])
        self.assertEqual(process["skirt_loops"], "1")
        self.assertEqual(process["skirt_speed"], "10")
        self.assertEqual(process["post_process"], [])
        self.assertEqual(filament["filament_diameter"], ["1.75"])
        self.assertEqual(filament["nozzle_temperature"], ["220"])
        self.assertNotIn("E17.4017", machine["machine_start_gcode"])

    def test_public_sources_and_license_are_present_hash_bound_and_not_host_caches(self):
        manifest = json.loads((PROFILES / "provenance.json").read_text())
        license_path = PROFILES / "LICENSE.txt"
        self.assertIn("GNU AFFERO GENERAL PUBLIC LICENSE", license_path.read_text())
        self.assertEqual(hashlib.sha256(license_path.read_bytes()).hexdigest(), manifest["license_sha256"])
        self.assertEqual(len(manifest["upstream_sources"]), 8)
        listed = set()
        for source in manifest["upstream_sources"]:
            path = PROFILES / source["path"]
            self.assertTrue(path.resolve().is_relative_to(PROFILES.resolve()))
            self.assertTrue(source["url"].startswith("https://raw.githubusercontent.com/OrcaSlicer/OrcaSlicer/v2.5.0/resources/profiles/"))
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), source["sha256"])
            json.loads(path.read_text())
            listed.add(path)
        self.assertEqual(set((PROFILES / "upstream").rglob("*.json")), listed)
        self.assertFalse(list(PROFILES.rglob("*.opc")))
        self.assertFalse(list(PROFILES.rglob("*.bin")))

    def test_reviewed_json_contains_no_host_identity_network_or_credential_fields(self):
        # Regression aid only; not a substitute for manual privacy/license review.
        paths = [PROFILES / (kind + ".json") for kind in ("machine", "process", "filament")]
        for path in paths + list((PROFILES / "upstream").rglob("*.json")):
            text = path.read_text()
            self.assertNotRegex(text, r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
            self.assertNotRegex(text, r"(?i)\b(?:[0-9a-f]{2}:){5}[0-9a-f]{2}\b")
            self.assertNotIn("/home/", text)
            self.assertNotIn("/Users/", text)
            config = json.loads(text)
            for key in config:
                self.assertIsNone(re.search(r"(?i)(password|api_key|access_token|serial_number|host_address)", key))

    def test_native_launcher_points_to_tracked_profile_not_private_draft(self):
        spec = importlib.util.spec_from_file_location("bundled_launcher", ROOT / "tools/start_offline_web.py")
        launcher = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(launcher)
        self.assertEqual(launcher.PROFILE, PROFILES)
        # No executable lookup or listeners/native/printer connections here.
