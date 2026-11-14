"""Offline numerical diagnostics only; these checks cannot certify motion safety."""

import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import unittest

from finderlab.gcode_review import LIMIT, code_bytes, review, review_file
from helpers import workspace_tempdir


class ReviewTests(unittest.TestCase):
    def test_absolute_e_reset_and_bad_copied_end(self):
        bad = b"G90\nM82\nG92 E0\nG1 E417.17445 F1200\nG1 E415.17445\nG1 E778.4812\n"
        data = review(bad)
        self.assertAlmostEqual(data["last_e_move"]["delta_mm"], 363.30675)
        self.assertTrue(any("Large positive E-only" in x for x in data["alerts"]))
        good = review(b"G90\nM82\nG92 E0\nG1 X55 E17.4017\nG92 E0\nG1 E-1.3 F1800\nG92 E0\nG1 E1.3\nG1 X1 E2.5\nG1 E1.2\n")
        self.assertEqual(good["last_e_move"]["delta_mm"], -1.3)
        self.assertEqual(good["largest_positive_e_only"]["delta_mm"], 1.3)
        self.assertFalse(good["alerts"])
        self.assertIn("NOT PRINT APPROVAL", good["status"])

    def test_unknown_origin_and_extrusion_mode_are_not_silently_zero(self):
        d = review(b"G90\nG1 E17\nG1 E-2\n")
        self.assertEqual(d["unresolved_e_moves"], 2)
        d = review(b"G90\nG1 E17\nG1 E-2\n", assume_absolute_e=True)
        self.assertTrue(d["absolute_e_assumption"])
        self.assertEqual(d["unresolved_e_moves"], 1)
        self.assertEqual(d["last_e_move"]["delta_mm"], -19)
        d = review(b"G90\nM83\nG1 E-1.3\nG1 E1.3\n")
        self.assertEqual(d["last_e_move"]["delta_mm"], 1.3)
        d = review(b"M83\nG90\nG1 E100\n")
        self.assertEqual(d["unresolved_e_moves"], 1)

    def test_gx_offset_and_limits(self):
        body = b"G21\nG90\nG1 X71 Y-71 Z141 F420\n"
        header = bytearray(58)
        header[:12] = b"xgcode 1.0\n\x00"
        struct.pack_into("<I", header, 20, 58)
        d = review(bytes(header) + body)
        self.assertEqual(d["gx_offset"], 58)
        self.assertEqual(len(d["alerts"]), 3)
        for raw in (b"", b"GCDE\x00", b"xgcode 1.0", b"xgcode 1.0" + bytes(30)):
            with self.subTest(raw=raw), self.assertRaises(ValueError): code_bytes(raw)

    def test_mixed_xyz_feed_is_not_z_axis_speed_and_split_is_distinct(self):
        common = b"G21\nG90\nG1 X0 Y0 Z0 F420\n"
        combined = review(common + b"G1 X0.01 Y0 Z0.18 F4800\n")
        self.assertGreater(combined["max_resolved_z_component_mm_s"], 79)
        split = review(common + b"G1 Z0.18 F420\nG1 X0.01 Y0 Z0.18 F4800\n")
        self.assertEqual(split["max_resolved_z_component_mm_s"], 7)
        self.assertEqual(split["max_feed_on_z_moves_mm_min"], 4800)
        self.assertEqual(split["unresolved_z_segments"], 1)

    def test_homing_is_unmodeled_and_section_markers_are_not_footer_substrings(self):
        data = review(b"; FINDER02_START_BEGIN\nG90\nG28\nG1 X55 Y20 F4800\n; FINDER02_START_END\nG1 X10 Y10\n; FINDER02_END_BEGIN\nG162 Z F1800\nG28 X Y\n; machine_start_gcode = ; FINDER02_START_BEGIN\\nG1 X999\n")
        self.assertEqual(data["section_bounds_mm"]["start"]["X"], [55, 55])
        self.assertEqual(data["section_bounds_mm"]["body"]["X"], [10, 10])
        self.assertEqual(data["section_bounds_mm"]["end"]["X"], [None, None])
        self.assertEqual(len(data["unmodeled_homing_offsets"]), 3)
        self.assertIn("Homing/offset paths", data["limitations"][1])

    def test_unsupported_line_invalidates_subsequent_modal_inference(self):
        d = review(b"G90\nM82\nG92 E0\nG1 E99 (unmodeled syntax)\nG1 E100\n")
        self.assertTrue(d["parse_warnings"])
        self.assertEqual(d["unresolved_e_moves"], 1)
        self.assertIsNone(d["last_e_move"])

    def test_regular_file_limits_and_fifo_refusal(self):
        with workspace_tempdir() as directory:
            path = Path(directory) / "source.gcode"
            path.write_bytes(b"")
            with self.assertRaises(ValueError): review_file(path)
            with path.open("wb") as writer: writer.truncate(LIMIT + 1)
            with self.assertRaises(ValueError): review_file(path)
            if hasattr(os, "mkfifo"):
                pipe = Path(directory) / "pipe.gcode"
                os.mkfifo(pipe)
                with self.assertRaises(ValueError): review_file(pipe)

    def test_bounded_syntax_and_no_network_cli(self):
        with self.assertRaises(ValueError): review(b";" + b"x" * 5000)
        self.assertTrue(review(b"G90\nG1 X1 X2\n")["parse_warnings"])
        with workspace_tempdir() as directory:
            source = Path(directory) / "synthetic.gcode"
            source.write_bytes(b"G21\nG90\nM82\nG92 E0\nG1 X1 Y1 E1\nG1 E-.3\n")
            result = subprocess.run([sys.executable, "-m", "finderlab", "review", str(source)],
                                    capture_output=True, timeout=5)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["last_e_move"]["delta_mm"], -1.3)
