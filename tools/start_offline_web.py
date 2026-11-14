#!/usr/bin/env python3
"""Start the local draft-02 slicing page with all printer actions disabled."""

import argparse
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
PROFILE = ROOT / "local-profiles/finder-offline-02"
ORCA = ROOT / ".local-tools/OrcaSlicer_Linux_AppImage_Ubuntu2404_V2.5.0.AppImage"
FALLBACK_ORCA = ROOT / ".local-tools/orca-slicer"


def build_command(port=8000, orca=None):
    if sys.version_info < (3, 11):
        raise ValueError("Python 3.11 or newer is required")
    if not 1 <= port <= 65535:
        raise ValueError("Port must be between 1 and 65535")
    if orca is not None:
        selected = Path(orca).expanduser()
    else:
        selected = ORCA if ORCA.exists() else FALLBACK_ORCA
    if not selected.is_absolute():
        selected = ROOT / selected
    if not selected.is_file() or not os.access(selected, os.X_OK):
        raise ValueError("Local Orca launcher missing/not executable: " + str(selected))
    command = [sys.executable, "-m", "finderlab", "web", "--listen-host", "127.0.0.1",
               "--listen-port", str(port), "--target-port", "9000", "--data-dir", str(ROOT / "web-data/offline-test"),
               "--orca", str(selected.resolve())]
    for kind in ("machine", "process", "filament"):
        path = PROFILE / (kind + ".json")
        if not path.is_file() or not 0 < path.stat().st_size <= 1024 * 1024:
            raise ValueError("Local draft-02 profile missing/invalid: " + str(path)
                             + ". Private profiles are not included in a fresh Git clone; see docs/ORCA_FINDER_DRAFT_02.md")
        command += ["--" + kind, str(path)]
    # Deliberately no arbitrary argument forwarding or printer-enable flags.
    return command


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--port", type=int, default=8000, help="loopback HTTP port (default: 8000)")
    cli.add_argument("--orca", type=Path, help="trusted native Orca executable; relative paths are project-relative")
    cli.add_argument("--check", action="store_true", help="check local files only; do not launch anything")
    args = cli.parse_args()
    try:
        command = build_command(args.port, args.orca)
    except ValueError as exc:
        cli.error(str(exc))
    print("OFFLINE SLICING ONLY: printer uploads, Start and Cancel are disabled.", flush=True)
    print("Draft 02 is experimental and NOT approved for printing.", flush=True)
    print("Orca: " + command[command.index("--orca") + 1], flush=True)
    print("Profile/output review used 2.3.0; another build requires new offline output review.", flush=True)
    print("Open http://127.0.0.1:" + str(args.port), flush=True)
    print("Test cube: " + str(PROFILE / "review/cube-20x20x5.stl"), flush=True)
    if args.check:
        print("Local file checks passed; native runtime libraries are not probed.", flush=True)
        return
    os.chdir(ROOT)
    os.execv(sys.executable, command)


if __name__ == "__main__":
    main()
