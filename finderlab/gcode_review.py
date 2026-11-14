"""Offline command-coordinate/E-delta diagnostics, NOT a print-safety validator.

No sockets, native programs, code rewriting or hardware execution. Homing,
firmware offsets and physical swept volumes cannot be inferred by this tool.
"""

from collections import Counter
import hashlib
import io
import math
import os
from pathlib import Path
import re
import struct
import stat

COMMAND = re.compile(r"^([GMT]\d+(?:\.\d+)?)(?:\s|(?=[XYZEFST]))", re.I)
WORD = re.compile(r"([A-Z])([+-]?(?:\d+(?:\.\d*)?|\.\d+))", re.I)
LIMIT = 64 * 1024 * 1024


def code_bytes(data):
    if not data:
        raise ValueError("Empty review input")
    if len(data) > LIMIT:
        raise ValueError("Review input exceeds 64 MiB")
    if data.startswith(b"xgcode 1.0"):
        if len(data) < 28:
            raise ValueError("Truncated GX header")
        offset = struct.unpack_from("<I", data, 20)[0]
        if not 28 <= offset < len(data):
            raise ValueError("Invalid GX code offset")
        return data[offset:], offset
    if b"\x00" in data:
        raise ValueError("Expected plain G-code or the observed xgcode 1.0 container")
    return data, 0


def review(data, *, assume_absolute_e=False):
    code, offset = code_bytes(data)
    text = code.decode("utf-8")
    if "\x00" in text:
        raise ValueError("NUL in G-code body")
    commands = Counter()
    bounds = {axis: [None, None] for axis in "XYZ"}
    section_bounds = {s: {a: [None, None] for a in "XYZ"} for s in ("start", "body", "end")}
    position = {axis: None for axis in "XYZ"}
    e = None
    e_mode = "absolute_assumed" if assume_absolute_e else None
    xyz_relative = None
    scale, feed = 1.0, None
    section = "body"
    explicit_units = False
    motion_before_units = 0
    e_moves = e_unknown = 0
    positive = negative = 0.0
    largest = []
    last_e = None
    resets = 0
    unmodeled = []
    parse_warnings = []
    z_feeds = []
    max_z_feed = None
    max_positive_e_only = None
    max_resolved_z_component = None
    unresolved_z_segments = 0
    extrusion_alerts = []

    def warn(line, message):
        if len(parse_warnings) < 30:
            parse_warnings.append({"line": line, "message": message})

    def extend(bucket, axis, value):
        lo, hi = bucket[axis]
        bucket[axis] = [value if lo is None else min(lo, value), value if hi is None else max(hi, value)]

    number = 0
    for number, raw in enumerate(io.StringIO(text), 1):
        if len(raw) > 4096 or number > 2_000_000:
            raise ValueError("Review line length/count exceeds limit")
        comment = raw.strip().lower()
        if comment in ("; finder02_start_begin", ";start gcode"):
            section = "start"
        elif comment in ("; finder02_start_end", ";raft") or comment.startswith((";layer:", ";layer_change")):
            section = "body"
        elif comment in ("; finder02_end_begin", ";end gcode"):
            section = "end"
        line = raw.partition(";")[0].strip().upper()
        if not line:
            continue
        match = COMMAND.match(line + " ")
        if not match or "(" in line or "*" in line:
            warn(number, "Unsupported line syntax; subsequent modal state is unresolved")
            position = {axis: None for axis in "XYZ"}
            e = e_mode = xyz_relative = feed = None
            continue
        command = match[1]
        commands[command] += 1
        if len(commands) > 128:
            raise ValueError("Too many distinct command codes")
        tail = line[match.end():]
        words = WORD.findall(tail)
        if command in ("G0", "G1", "G92") and (WORD.sub("", tail).strip() or len({a for a, _ in words}) != len(words)
                or set(a for a, _ in words) - set("XYZE" if command == "G92" else "XYZEF")):
            warn(number, "Ambiguous/unsupported motion parameters; no inference")
            position = {axis: None for axis in "XYZ"}
            e = None
            continue
        values = {}
        for axis, value in words:
            if axis in values:
                warn(number, "Repeated parameter; interpretation is ambiguous")
            value = float(value)
            if not math.isfinite(value) or abs(value) > 1e9:
                raise ValueError(f"Non-finite/out-of-range numeric field at line {number}")
            values[axis] = value
        if command in ("G20", "G21"):
            scale = 25.4 if command == "G20" else 1.0
            explicit_units = True
        elif command in ("G90", "G91"):
            xyz_relative = command == "G91"
            # Some firmwares couple G90/G91 to E mode. Only subsequent explicit
            # M82/M83 or a named caller assumption resolves this diagnostic.
            expected = "relative" if xyz_relative else "absolute"
            if e_mode in ("absolute", "relative", "absolute_assumed") and e_mode.removesuffix("_assumed") != expected:
                e_mode = None
                warn(number, "G90/G91 may affect E mode; wait for explicit M82/M83")
            elif e_mode is None and not xyz_relative and assume_absolute_e:
                e_mode = "absolute_assumed"
        elif command in ("M82", "M83"):
            e_mode = "absolute" if command == "M82" else "relative"
        elif command == "G92":
            for axis in "XYZ":
                if axis in values:
                    position[axis] = values[axis] * scale
            if "E" in values:
                e = values["E"] * scale
                resets += 1
        elif command in ("G28", "G161", "G162", "M132"):
            if len(unmodeled) < 50:
                unmodeled.append({"line": number, "command": command, "section": section})
            # These paths/offsets (including A/B extruder references) are not
            # known physical coordinates or reliable E origins.
            position = {axis: None for axis in "XYZ"}
            e = None
        elif command in ("G0", "G1"):
            if "F" in values:
                feed = values["F"] * scale
            moving = [axis for axis in "XYZ" if axis in values]
            if not explicit_units and (moving or "E" in values):
                motion_before_units += 1
            before = dict(position)
            for axis in moving:
                value = values[axis] * scale
                if xyz_relative is None:
                    position[axis] = None
                    warn(number, "XYZ mode unknown")
                elif xyz_relative:
                    position[axis] = None if position[axis] is None else position[axis] + value
                else:
                    position[axis] = value
                if position[axis] is not None:
                    extend(bounds, axis, position[axis])
                    extend(section_bounds[section], axis, position[axis])
            if "Z" in moving and feed is not None:
                if all(before[a] is not None and position[a] is not None for a in moving):
                    length = math.sqrt(sum((position[a] - before[a]) ** 2 for a in moving))
                    component = 0 if not length else feed / 60 * abs(position["Z"] - before["Z"]) / length
                    max_resolved_z_component = component if max_resolved_z_component is None else max(max_resolved_z_component, component)
                else:
                    unresolved_z_segments += 1
                max_z_feed = feed if max_z_feed is None else max(max_z_feed, feed)
            if "Z" in moving and len(z_feeds) < 20:
                z_feeds.append({"line": number, "feed_mm_min": feed, "z": position["Z"], "mixed_xy": bool(set(moving) & {"X", "Y"})})
            if "E" in values:
                target = values["E"] * scale
                delta = target if e_mode == "relative" else None if e is None or e_mode is None else target - e
                e = None if e_mode is None else target if e_mode.startswith("absolute") else None if e is None else e + target
                e_moves += 1
                if delta is None:
                    e_unknown += 1
                else:
                    positive += max(delta, 0)
                    negative += min(delta, 0)
                    event = {"line": number, "delta_mm": round(delta, 6), "e_only": not moving,
                             "section": section, "feed_mm_min": feed}
                    if event["e_only"] and delta > 0:
                        if max_positive_e_only is None or delta > max_positive_e_only["delta_mm"]:
                            max_positive_e_only = event
                        if delta > 10 and len(extrusion_alerts) < 30:
                            extrusion_alerts.append(f"Large positive E-only move at line {number}: {delta:.6f} mm")
                    largest.append(event)
                    largest.sort(key=lambda x: abs(x["delta_mm"]), reverse=True)
                    del largest[12:]
                    last_e = event
        elif (command.startswith("G") and command != "G4") or command.startswith("T") or command in ("M200", "M206", "M218", "M221", "M600"):
            warn(number, f"{command} is not modeled; endpoint/path/extrusion checks are incomplete")
            position = {axis: None for axis in "XYZ"}
            e = None

    alerts = []
    for axis, (lo, hi) in bounds.items():
        limit = 70 if axis != "Z" else 140
        minimum = -70 if axis != "Z" else 0
        if lo is not None and (lo < minimum or hi > limit):
            alerts.append(f"Declared {axis} endpoint outside nominal [{minimum}, {limit}]")
    alerts.extend(extrusion_alerts)
    if max_resolved_z_component is not None and max_resolved_z_component > 7.000001:
        alerts.append(f"Nominal resolved Z component exceeds reference 7 mm/s: {max_resolved_z_component:.6f} mm/s")
    return {"status": "OFFLINE DIAGNOSTICS ONLY — NOT PRINT APPROVAL", "sha256": hashlib.sha256(data).hexdigest(),
            "gx_offset": offset, "lines": number, "commands": dict(sorted(commands.items())),
            "bounds_mm": bounds, "section_bounds_mm": section_bounds,
            "units": "explicit G20/G21 seen; prefix may still assume mm" if explicit_units else "mm ASSUMED; units not explicitly selected",
            "motions_before_explicit_units": motion_before_units,
            "review_reference": {"nominal_xy_mm": [-70, 70], "nominal_z_mm": [0, 140], "z_speed_mm_s": 7, "not_measured_clearance": True},
            "absolute_e_assumption": assume_absolute_e, "e_moves": e_moves, "unresolved_e_moves": e_unknown,
            "g92_e_resets": resets, "positive_e_mm": round(positive, 6), "negative_e_mm": round(negative, 6),
            "largest_e_deltas": largest, "largest_positive_e_only": max_positive_e_only,
            "last_e_move": last_e, "first_z_feed_samples": z_feeds,
            "max_feed_on_z_moves_mm_min": max_z_feed,
            "max_resolved_z_component_mm_s": max_resolved_z_component, "unresolved_z_segments": unresolved_z_segments,
            "unmodeled_homing_offsets": unmodeled, "parse_warnings": parse_warnings, "alerts": alerts,
            "limitations": ["No firmware semantics or collision guarantee", "Homing/offset paths and physical swept volumes are unknown",
                            "Bounds describe commanded endpoints, not measured nozzle/bed clearance", "Missing alerts do not imply safety"]}


def review_file(path, **options):
    path = Path(path)
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_BINARY", 0))
    with os.fdopen(descriptor, "rb") as reader:
        before = os.fstat(reader.fileno())
        if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= LIMIT:
            raise ValueError("Review requires a nonempty regular file, at most 64 MiB")
        data = reader.read(LIMIT + 1)
        after = os.fstat(reader.fileno())
        if len(data) != before.st_size or (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (after.st_size, after.st_mtime_ns, after.st_ctime_ns):
            raise ValueError("Source changed during review; no reliable snapshot")
    return review(data, **options)
