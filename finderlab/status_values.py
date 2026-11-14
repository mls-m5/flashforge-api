"""Parse observed status reply bodies, without transport or completion inference."""

import re


def decode_status_body(code, body):
    if len(body) > 4096 or re.search(rb"(?:^|\r\n)(?:error|failed|resend)", body, re.I):
        return None
    if code == "M105":
        match = re.search(rb"(?:^|\r\n)T0:([0-9]{1,3}(?:\.[0-9]{1,2})?) /([0-9]{1,3}(?:\.[0-9]{1,2})?) B:([0-9]{1,3}(?:\.[0-9]{1,2})?) /([0-9]{1,3}(?:\.[0-9]{1,2})?)(?:\r\n|$)", body)
        if match:
            return dict(zip(("nozzle", "nozzle_target", "bed", "bed_target"), map(float, match.groups())))
    elif code == "M119":
        machine = re.search(rb"(?:^|\r\n)MachineStatus: ([A-Z_]{1,64})(?:\r\n|$)", body)
        move = re.search(rb"(?:^|\r\n)MoveMode: ([A-Z_]{1,64})(?:\r\n|$)", body)
        if machine and move:
            return {"machine": machine[1].decode(), "move": move[1].decode()}
    elif code == "M27":
        progress = re.fullmatch(rb"SD printing byte ([0-9]{1,12})/([0-9]{1,12})", body)
        if progress:
            done, total = map(int, progress.groups())
            return {"done": done, "total": total, "percent": None if total == 0 else min(100, 100 * done / total),
                    "over_total": done > total, "completion_inferred": False}
        if body == b"Not SD printing":
            return {"done": None, "total": None, "percent": None, "over_total": False, "completion_inferred": False}
    return None
