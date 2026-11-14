"""Synthetic control counters only; not physical travel/extrusion evidence."""

import math
import unittest

from finderlab.manual_controls import StaleControls, VirtualControls


class VirtualControlTests(unittest.TestCase):
    def setUp(self):
        self.controls = VirtualControls()

    def apply(self, action, **fields):
        value = {"action": action, "confirm": True, "revision": self.controls.state["revision"], **fields}
        self.controls.state = self.controls.prepare(value)

    def test_prepare_is_pure_and_snapshots_do_not_mutate_state(self):
        rgb = [136, 138, 133]
        candidate = self.controls.prepare({"action": "light", "rgb": rgb, "revision": 0, "confirm": True})
        rgb[0] = 0
        self.assertEqual(candidate["rgb"], [136, 138, 133])
        self.assertEqual(self.controls.state["rgb"], [0, 0, 0])
        snapshot = self.controls.snapshot(); snapshot["offsets_mm"]["X"] = 1000
        self.assertEqual(self.controls.state["offsets_mm"]["X"], 0)

    def test_xyz_single_steps_and_cumulative_counter_bounds(self):
        for _ in range(10): self.apply("jog", axis="X", distance=.1)
        self.assertEqual(self.controls.state["offsets_mm"]["X"], 1)
        self.apply("jog", axis="Y", distance=-5)
        self.apply("jog", axis="Z", distance=-1)
        self.apply("jog", axis="Y", distance=-5)
        with self.assertRaises(ValueError): self.apply("jog", axis="Y", distance=-.1)
        self.assertEqual(self.controls.state["offsets_mm"], {"X": 1, "Y": -10, "Z": -1})

    def test_cold_extrusion_locked_both_directions_then_warm_rehearsal_and_limits(self):
        for direction in (-1, 1):
            with self.assertRaisesRegex(ValueError, "cold-locked"):
                self.apply("extrude", distance=direction)
        self.apply("warm", enabled=True)
        for _ in range(4): self.apply("extrude", distance=5)
        with self.assertRaises(ValueError): self.apply("extrude", distance=1)
        self.apply("extrude", distance=-1)
        self.assertEqual(self.controls.state["extruded_mm"], 19)
        self.apply("warm", enabled=False)
        with self.assertRaises(ValueError): self.apply("extrude", distance=-5)

    def test_duplicate_revision_cannot_repeat_a_step(self):
        command = {"action": "jog", "axis": "X", "distance": 1, "confirm": True, "revision": 0}
        self.controls.state = self.controls.prepare(command)
        with self.assertRaises(StaleControls): self.controls.prepare(command)
        self.assertEqual(self.controls.state["offsets_mm"]["X"], 1)

    def test_exact_typed_allowlist_no_raw_command_or_continuous_motion(self):
        invalid = [
            {"action": "command", "command": "G1 X1000"}, {"action": "home"}, {"action": "stop"},
            {"action": "jog", "axis": "XY", "distance": 1}, {"action": "jog", "axis": "E", "distance": 1},
            {"action": "jog", "axis": "Z", "distance": 5}, {"action": "jog", "axis": "X", "distance": 1000},
            {"action": "jog", "axis": "X", "distance": 1, "feed": 100},
            {"action": "light", "rgb": [0, 0, 256]}, {"action": "light", "rgb": [0, False, 0]},
            {"action": "light", "rgb": [0.0, 0, 0]}, {"action": "light", "rgb": "#ffffff"},
            {"action": "warm", "enabled": 1}, {"action": ["jog"]},
        ]
        for value in (True, "1", math.nan, math.inf, -math.inf, 10**1000, 0, .5):
            invalid.append({"action": "jog", "axis": "X", "distance": value})
        for fields in invalid:
            with self.subTest(fields=fields), self.assertRaises(ValueError):
                self.controls.prepare({"confirm": True, "revision": 0, **fields})
        self.assertEqual(self.controls.state["revision"], 0)

    def test_confirmation_and_revision_types(self):
        for confirm, revision in ((False, 0), (1, 0), (True, True), (True, 0.0), (True, -1)):
            with self.assertRaises(ValueError):
                self.controls.prepare({"confirm": confirm, "revision": revision, "action": "light", "rgb": [0, 0, 0]})
