"""Synthetic responses, not a captured or verified Finder 2 profile.

Command names come from the hypotheses in docs/PROTOCOL.md. Response formatting,
identity, error semantics, and status values here are local test conventions.
"""

PROFILE_ID = "synthetic-v1"

STATUS_RESPONSES = {
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


def response(command: str, body: str = "") -> bytes:
    """Build a synthetic success reply. Errors deliberately do not end in ok."""
    lines = [f"CMD {command} Received."]
    if body:
        lines.append(body)
    lines.append("ok")
    return ("\r\n".join(lines) + "\r\n").encode("ascii")
