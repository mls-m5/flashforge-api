"""Typed virtual control rehearsal. Intentionally has NO wire-command encoder.

Counters and warm-nozzle flag are invented UI-test state, not printer physics,
position, temperature, limits or proof of Finder millimetre-mode semantics.
"""

from copy import deepcopy
import math


class VirtualControls:
    def __init__(self):
        self.state = {"revision": 0, "rgb": [0, 0, 0], "offsets_mm": {a: 0.0 for a in "XYZ"},
                      "extruded_mm": 0.0, "warm_nozzle_simulated": False}

    def snapshot(self):
        return deepcopy(self.state)

    def prepare(self, data):
        """Return a candidate only; caller must record successfully before commit."""
        if not isinstance(data, dict) or data.get("confirm") is not True:
            raise ValueError("Explicit confirmation required")
        if type(data.get("revision")) is not int or data["revision"] != self.state["revision"]:
            raise StaleControls("Control state changed; refresh before a new confirmation")
        action = data.get("action")
        fields = {"light": {"rgb"}, "jog": {"axis", "distance"}, "extrude": {"distance"}, "warm": {"enabled"}}
        if not isinstance(action, str) or action not in fields or set(data) != {"confirm", "revision", "action"} | fields[action]:
            raise ValueError("Only documented typed manual actions are accepted; no commands/targets")
        result = self.snapshot()
        if action == "light":
            rgb = data["rgb"]
            if not isinstance(rgb, list) or len(rgb) != 3 or any(type(n) is not int or not 0 <= n <= 255 for n in rgb):
                raise ValueError("RGB needs exactly three integers from 0 to 255")
            result["rgb"] = rgb.copy()
        elif action == "warm":
            if type(data["enabled"]) is not bool:
                raise ValueError("Simulated warm-nozzle flag must be boolean")
            result["warm_nozzle_simulated"] = data["enabled"]
        else:
            value = data["distance"]
            if type(value) not in (int, float) or abs(value) > 5 or not math.isfinite(value):
                raise ValueError("Step must be a finite number, not text or a boolean")
            if action == "jog":
                axis = data["axis"]
                if not isinstance(axis, str) or axis not in ("X", "Y", "Z"):
                    raise ValueError("Choose exactly one of X, Y, Z")
                allowed = (0.1, 1) if axis == "Z" else (0.1, 1, 5)
                if abs(value) not in allowed:
                    raise ValueError("XY steps: 0.1/1/5 mm; Z steps: 0.1/1 mm")
                total = round(result["offsets_mm"][axis] + value, 1)
                if abs(total) > 10:
                    raise ValueError("Virtual relative counter limit is ±10 mm; this is NOT a physical travel limit")
                result["offsets_mm"][axis] = total
            else:
                if abs(value) not in (1, 5):
                    raise ValueError("Extruder rehearsal steps: 1 or 5 mm")
                if not result["warm_nozzle_simulated"]:
                    raise ValueError("Extruder rehearsal is cold-locked; explicitly simulate warm nozzle first (no heating)")
                total = result["extruded_mm"] + value
                if abs(total) > 20:
                    raise ValueError("Virtual extrusion counter limit is ±20 mm")
                result["extruded_mm"] = total
        result["revision"] += 1
        return result


class StaleControls(ValueError):
    pass
