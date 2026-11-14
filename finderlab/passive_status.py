"""Bounded, read-only status derived from existing proxy recordings; no sockets."""

from datetime import datetime, timezone
import json
import os
import stat
from pathlib import Path
import re

EVENT_TAIL = 256 * 1024
STREAM_TAIL = 64 * 1024
STALE_SECONDS = 10
FRAME = re.compile(rb"CMD (M105|M119|M27) Received\.\r\n((?:(?!CMD )[^\x00]){0,4096}?)\r\nok\r\n")


def tail(path, limit):
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
    with os.fdopen(descriptor, "rb") as file:
        if not stat.S_ISREG(os.fstat(file.fileno()).st_mode):
            raise ValueError("Expected a regular capture stream")
        file.seek(0, 2)
        size = file.tell()
        offset = max(0, size - limit)
        file.seek(offset)
        return offset, file.read(limit)


def manifest(path):
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 1024 * 1024:
        raise ValueError("Invalid/big capture manifest")
    with path.open("rb") as file:
        raw = file.read(1024 * 1024 + 1)
    if len(raw) > 1024 * 1024:
        raise ValueError("Capture manifest grew beyond limit")
    return json.loads(raw)


def capture_path(source, host, port):
    source = Path(source)
    if source.is_symlink():
        raise ValueError("Symlink status source is not supported")
    direct = (source / "manifest.json").is_file()
    candidates = [source] if direct else []
    if not direct:
        for index, p in enumerate(source.iterdir()):
            if index >= 1024:
                raise ValueError("Too many capture entries; choose an explicit run directory")
            if p.is_dir() and not p.is_symlink():
                candidates.append(p)
        candidates.sort(key=lambda p: p.name, reverse=True)
    for folder in candidates:
        try:
            data = manifest(folder / "manifest.json")
            config = data.get("metadata", {}).get("config", {})
            if data.get("mode") == "proxy" and config.get("host") == host and config.get("port") == port:
                return folder, data
        except (OSError, ValueError, AttributeError, TypeError, RecursionError):
            if direct:
                raise
    raise ValueError("No proxy capture matches the configured loopback target host/port")


def status_from_capture(source, host, port, *, now=None):
    result = {"enabled": source is not None, "passive": True, "source": "", "session": "",
              "stale": True, "message": "Passive status is not configured", "samples": {},
              "capture_finalized": None, "upstream": "", "stale_seconds": STALE_SECONDS}
    if source is None:
        return result
    now = now or datetime.now(timezone.utc)
    try:
        folder, data = capture_path(source, host, port)
        result.update(source=folder.name, capture_finalized=data.get("complete") is True)
        config = data["metadata"]["config"]
        result["upstream"] = f"{config.get('target_host', 'unknown')}:{config.get('target_port', 'unknown')}"
        event_file = folder / "events.jsonl"
        if event_file.is_symlink():
            raise ValueError("Symlink event stream")
        _, raw_events = tail(event_file, EVENT_TAIL)
        events = []
        for line in raw_events.splitlines():
            try:
                e = json.loads(line)
                if (e.get("type") == "data" and e.get("direction") == "server_to_client"
                        and re.fullmatch(r"s[0-9]{4,10}", e.get("session_id", ""))
                        and type(e.get("stream_offset")) is int and e["stream_offset"] >= 0
                        and type(e.get("length")) is int and 0 < e["length"] <= 65536):
                    events.append(e)
            except (ValueError, AttributeError, TypeError, RecursionError):
                continue  # Tail may start/end within a JSON event while recording.
        # Use one session's replies only; never mix old temperature from another
        # session with a fresh status and call it all current.
        sessions = list(dict.fromkeys(e["session_id"] for e in reversed(events)))[:16]
        for session in sessions:
            path = folder / "sessions" / session / "server-to-client.bin"
            if path.is_symlink() or path.parent.is_symlink() or path.parent.parent.is_symlink():
                continue
            offset, stream = tail(path, STREAM_TAIL)
            samples = {}
            for match in FRAME.finditer(stream):
                end = offset + match.end() - 1
                e = next((e for e in reversed(events) if e["session_id"] == session
                          and e["stream_offset"] <= end < e["stream_offset"] + e["length"]), None)
                if e is None:
                    continue  # No authoritative observation time within bounded tail.
                try:
                    stamp = datetime.fromisoformat(e["utc"])
                    age = (now - stamp).total_seconds()
                    if not stamp.tzinfo:
                        continue
                except (KeyError, TypeError, ValueError):
                    continue
                body = match[2]
                code = match[1].decode("ascii")
                values = None
                if code == "M105":
                    temperature = re.search(rb"(?:^|\r\n)T0:([0-9]{1,3}(?:\.[0-9]{1,2})?) /([0-9]{1,3}(?:\.[0-9]{1,2})?) B:([0-9]{1,3}(?:\.[0-9]{1,2})?) /([0-9]{1,3}(?:\.[0-9]{1,2})?)(?:\r\n|$)", body)
                    if temperature:
                        values = dict(zip(("nozzle", "nozzle_target", "bed", "bed_target"), map(float, temperature.groups())))
                elif code == "M119":
                    machine = re.search(rb"(?:^|\r\n)MachineStatus: ([A-Z_]{1,64})(?:\r\n|$)", body)
                    move = re.search(rb"(?:^|\r\n)MoveMode: ([A-Z_]{1,64})(?:\r\n|$)", body)
                    if machine and move:
                        values = {"machine": machine[1].decode(), "move": move[1].decode()}
                elif code == "M27":
                    progress = re.fullmatch(rb"SD printing byte ([0-9]{1,12})/([0-9]{1,12})", body)
                    if progress:
                        done, total = map(int, progress.groups())
                        values = {"done": done, "total": total, "percent": None if total == 0 else min(100, 100 * done / total),
                                  "over_total": done > total, "completion_inferred": False}
                    elif body == b"Not SD printing":
                        values = {"done": None, "total": None, "percent": None, "over_total": False, "completion_inferred": False}
                if re.search(rb"(?:^|\r\n)(?:error|failed|resend)", body, re.I):
                    values = None
                # A malformed newer frame invalidates that metric rather than
                # letting an older parsed value look current.
                samples[code] = {"values": values, "observed_utc": e["utc"], "age_seconds": round(max(0, age), 1),
                                 "stale": age < -5 or age > STALE_SECONDS or values is None}
            if samples:
                result.update(session=session, samples=samples, stale=any(s.get("stale", True) for s in
                              (samples.get(k, {}) for k in ("M105", "M119", "M27"))),
                              message="Observed proxy replies only; no printer requests sent. Byte progress is not time remaining or proof of completion.")
                return result
        result["message"] = "No complete timestamped status replies in the recent capture tail. FlashPrint must already be polling through this proxy."
    except (OSError, ValueError, TypeError, KeyError, AttributeError, RecursionError):
        result["message"] = "Cannot read a matching proxy capture; check the local status source and proxy listener. No printer connection was attempted."
    return result
