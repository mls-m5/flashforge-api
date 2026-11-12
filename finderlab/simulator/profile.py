"""Versioned response profiles: captured idle replies and the original mock.

The captured profile covers identity/control acquisition and idle queries only.
Upload framing, errors, control policy and release remain synthetic conventions.
See docs/PROTOCOL.md, observation FINDER-IDLE-003, for evidence and redactions.
"""

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

DEFAULT_PROFILE = "finder-v1.5-idle"

SYNTHETIC_RESPONSES = {
    "M115": (
        "Machine Type: Flashforge Finder 2\r\n"
        "Machine Name: FinderLab Mock\r\n"
        "Firmware: synthetic-v1\r\n"
        "SN: FINDERLAB0001\r\n"
        "X: 140 Y: 140 Z: 140\r\n"
        "Tool Count: 1\r\n"
        "Mac Address:02:00:00:00:00:01"
    ),
    "M105": "T0:25 /0 B:0 /0",
    "M114": "X:0.000 Y:0.000 Z:0.000 A:0.000 B:0",
    "M119": (
        "Endstop: X-max: 0 Y-max: 0 Z-min: 0\r\n"
        "MachineStatus: READY\r\n"
        "MoveMode: READY\r\n"
        "Status: S:1 L:0 J:0 F:0\r\n"
        "LED: 0\r\n"
        "CurrentFile:"
    ),
    "M27": "SD printing byte 0/0",
    # Observed as an incoming FlashPrint query in user report FP-M650-001.
    # XY reply shape is externally reported for other FlashForge models;
    # zero offsets are a synthetic choice, not a captured Finder 2 response.
    "M650": "X: 0 Y: 0",
}


FINDER_IDLE_RESPONSES = {
    "M115": (
        "Machine Type: Flashforge Finder\r\n"
        "Machine Name: Mock Find\r\n"
        "Firmware: V1.5 20170419\r\n"
        "SN: F1AB0001\r\n"
        "X: 140  Y: 140  Z: 140\r\n"
        "Tool Count: 1"
    ),
    "M650": "X: 34 Y: 0",
    "M114": "X:0 Y:0 Z:0 A:0 B:0",
    "M27": "SD printing byte 0/0",
    "M119": (
        "Endstop: X-max: 1 Y-max: 0 Z-max: 1\r\n"
        "Status: S:1 L:0 J:0 F:1\r\n"
        "MachineStatus: READY\r\n"
        "MoveMode: READY"
    ),
    "M105": "T0:21 /0 B:0 /0",
}


@dataclass(frozen=True)
class Profile:
    id: str
    firmware: str
    status_responses: Mapping[str, str]
    control_success: str
    source_capture: str | None = None


PROFILES = MappingProxyType({
    "synthetic-v1": Profile(
        "synthetic-v1", "synthetic-v1", MappingProxyType(SYNTHETIC_RESPONSES),
        "Control Success V2.1.",
    ),
    DEFAULT_PROFILE: Profile(
        DEFAULT_PROFILE, "V1.5 20170419", MappingProxyType(FINDER_IDLE_RESPONSES),
        "Control Success.", "20261112T190818Z-31ded6e5f0a5",
    ),
})


def response(command: str, body: str = "") -> bytes:
    """Build a CRLF success reply. Errors deliberately do not end in ok."""
    lines = [f"CMD {command} Received."]
    if body:
        lines.append(body)
    lines.append("ok")
    return ("\r\n".join(lines) + "\r\n").encode("ascii")
