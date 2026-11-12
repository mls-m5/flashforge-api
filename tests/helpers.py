"""Test helpers; generated files stay inside the ignored project-local .tmp/."""

import json
from pathlib import Path
import tempfile


def workspace_tempdir():
    root = Path(__file__).resolve().parents[1] / ".tmp"
    root.mkdir(mode=0o700, exist_ok=True)
    return tempfile.TemporaryDirectory(prefix="test-", dir=root)


def events(capture):
    return [json.loads(line) for line in (capture.path / "events.jsonl").read_text().splitlines()]


def stream(capture, session_id, direction):
    return (capture.path / "sessions" / session_id / (direction.replace("_", "-") + ".bin")).read_bytes()
