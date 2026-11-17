#!/usr/bin/env python3
"""Passive Linux listener readiness; NEVER connect through the recording proxy.

Host networking shares TCP tables, so match both the loopback LISTEN entry and
its socket inode in this container's actual finderlab proxy process. An unrelated
host listener must not make the bundled proxy healthy. No printer probes/polls.
"""

import os
from pathlib import Path
import sys


def bounded_text(path, limit):
    with path.open("rb") as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ValueError("Readiness input exceeds its bound")
    return data.decode("ascii")


def ready(port, proc=Path("/proc")):
    if not 1 <= port <= 65535:
        return False
    rows = bounded_text(proc / "net/tcp", 256 * 1024).splitlines()[1:]
    listener = f"0100007F:{port:04X}"
    inodes = set()
    for row in rows:
        fields = row.split()
        if len(fields) >= 10 and fields[1] == listener and fields[3] == "0A":
            inodes.add(fields[9])
    if not inodes:
        return False
    targets = {f"socket:[{inode}]" for inode in inodes}

    processes = [path for path in proc.iterdir() if path.name.isascii() and path.name.isdecimal()]
    if len(processes) > 512:
        return False
    for process in processes:
        try:
            argv = bounded_text(process / "cmdline", 16384).split("\0")
            if argv[1:4] != ["-m", "finderlab", "proxy"]:
                continue
            descriptors = list((process / "fd").iterdir())
            if len(descriptors) > 512:
                return False
            for descriptor in descriptors:
                try:
                    target = os.readlink(descriptor)
                except FileNotFoundError:
                    continue  # A descriptor may close while checking.
                if target in targets:
                    return True
        except (FileNotFoundError, ProcessLookupError):
            continue  # Process exited during this read-only check.
    return False


def main():
    try:
        raw = os.environ.get("FINDER_PROXY_PORT", "9000")
        if not raw.isascii() or not raw.isdecimal() or len(raw) > 10:
            return 1
        return 0 if ready(int(raw)) else 1
    except (OSError, ValueError):
        return 1


if __name__ == "__main__":
    sys.exit(main())
