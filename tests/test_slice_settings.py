"""Strict quality settings; no files, slicing or hardware required."""

import unittest

from finderlab.slice_settings import normalize_settings, process_overrides


class QualitySettingsTests(unittest.TestCase):
    def test_defaults_off_and_outer(self):
        self.assertEqual(process_overrides(None), {})
        self.assertEqual(process_overrides({"brim": "off"}), {"brim_type": "no_brim", "brim_width": "0"})
        self.assertEqual(process_overrides({"layer_height": 0.28, "brim": "outer", "brim_width": 4.5}),
                         {"layer_height": "0.28", "brim_type": "outer_only", "brim_width": "4.5"})
        self.assertIsNone(normalize_settings({})["layer_height"])

    def test_hole_compensation_is_per_edge_typed_and_profile_is_preserved_when_omitted(self):
        self.assertNotIn("xy_hole_compensation", normalize_settings({}))
        self.assertEqual(process_overrides({"xy_hole_compensation": None}), {})
        for value in (-0.5, -0.2, 0, 0.2, 0.5):
            self.assertEqual(process_overrides({"xy_hole_compensation": value}), {"xy_hole_compensation": format(value, ".8g")})
        for value in (True, "0.2", float("nan"), float("inf"), -float("inf"), -0.51, 0.51, 10**1000, [], {}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                normalize_settings({"xy_hole_compensation": value})
        with self.assertRaises(ValueError):
            normalize_settings({"xy_contour_compensation": 0.2})

    def test_rejects_non_numeric_non_finite_and_untrusted_keys(self):
        bad = [[], "outer", 2, {"post_process": ["shell"]}, {"machine_start_gcode": "G28"},
               {"brim": "auto_brim"}, {"brim": []}, {"layer_height": True}, {"layer_height": "0.12"},
               {"layer_height": 0.07}, {"layer_height": 0.29}, {"layer_height": float("nan")},
               {"brim_width": True}, {"brim_width": None}, {"brim_width": "5"},
               {"brim_width": 0}, {"brim_width": 11}, {"brim_width": float("inf")},
               {"brim_width": 10**1000}, {"layer_height": 10**1000}]
        for value in bad:
            with self.subTest(value=value), self.assertRaises(ValueError): normalize_settings(value)
