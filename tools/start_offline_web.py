#!/usr/bin/env python3
"""Start the local draft-02 slicing page with all printer actions disabled."""

import argparse
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
PROFILE = ROOT / "local-profiles/finder-offline-02"
ORCA = ROOT / ".local-tools/orca-2.5.0/AppRun"
ARCHIVE_ORCA = ROOT / ".local-tools/OrcaSlicer_Linux_AppImage_Ubuntu2404_V2.5.0.AppImage"
FALLBACK_ORCA = ROOT / ".local-tools/orca-slicer"


def build_command(port=8000, orca=None, *, dummy_upload_test=False, proxy_port=None,
                  enable_job_controls=False, allow_sliced_upload=False, status_capture=None):
    if dummy_upload_test and proxy_port is not None:
        raise ValueError("Choose owned dummy or proxy, not both")
    if proxy_port is not None and not 1 <= proxy_port <= 65535:
        raise ValueError("Proxy port must be between 1 and 65535")
    if proxy_port is None and status_capture is not None:
        raise ValueError("This launcher needs --proxy-port for passive proxy status")
    if proxy_port is None and (enable_job_controls or allow_sliced_upload):
        raise ValueError("Hardware-capable options require explicit --proxy-port")
    if sys.version_info < (3, 11):
        raise ValueError("Python 3.11 or newer is required")
    if not 1 <= port <= 65535:
        raise ValueError("Port must be between 1 and 65535")
    if orca is not None:
        selected = Path(orca).expanduser()
    else:
        if not ORCA.exists() and ARCHIVE_ORCA.exists():
            raise ValueError("Extracted Orca 2.5.0 AppRun is missing. Direct AppImage FUSE mounts fail the bounded workspace checks; see docs/ORCA_INSTALL.md")
        selected = ORCA if ORCA.exists() else FALLBACK_ORCA
    if not selected.is_absolute():
        selected = ROOT / selected
    if selected.suffix.lower() == ".appimage":
        raise ValueError("Use an extracted Orca AppRun, not a FUSE-mounted AppImage; see docs/ORCA_INSTALL.md")
    if not selected.is_file() or not os.access(selected, os.X_OK):
        raise ValueError("Local Orca launcher missing/not executable: " + str(selected))
    workspace = "web-data/proxy-test" if proxy_port is not None else "web-data/dummy-upload-test" if dummy_upload_test else "web-data/offline-test"
    command = [sys.executable, "-m", "finderlab", "web", "--listen-host", "127.0.0.1",
               "--listen-port", str(port), "--data-dir", str(ROOT / workspace), "--orca", str(selected.resolve())]
    if proxy_port is not None:
        source = Path(status_capture).expanduser() if status_capture is not None else ROOT / "captures"
        if not source.is_absolute():
            source = ROOT / source
        command += ["--target-host", "127.0.0.1", "--target-port", str(proxy_port), "--enable-upload",
                    "--status-capture", str(source)]
        if enable_job_controls:
            command += ["--enable-job-controls"]
        if allow_sliced_upload:
            command += ["--allow-sliced-upload"]
    else:
        command += ["--dummy"] if dummy_upload_test else ["--target-port", "9000"]
    for kind in ("machine", "process", "filament"):
        path = PROFILE / (kind + ".json")
        if not path.is_file() or not 0 < path.stat().st_size <= 1024 * 1024:
            raise ValueError("Local draft-02 profile missing/invalid: " + str(path)
                             + ". Private profiles are not included in a fresh Git clone; see docs/ORCA_FINDER_DRAFT_02.md")
        command += ["--" + kind, str(path)]
    # No arbitrary argument forwarding or direct hardware endpoint selection.
    return command


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--port", type=int, default=8000, help="loopback HTTP port (default: 8000)")
    cli.add_argument("--orca", type=Path, help="trusted native Orca executable; relative paths are project-relative")
    cli.add_argument("--dummy-upload-test", action="store_true", help="own a fresh dummy and permit save-only to it (no hardware endpoint)")
    cli.add_argument("--status-capture", type=Path, help="proxy mode: explicit existing capture run/root; default project captures")
    cli.add_argument("--proxy-port", type=int, help="enable Save to an explicitly chosen local proxy port (may reach hardware)")
    cli.add_argument("--enable-job-controls", action="store_true", help="with --proxy-port: enable separately confirmed Start/Cancel")
    cli.add_argument("--allow-sliced-upload", action="store_true", help="with --proxy-port: explicitly permit generated-output Save; NOT motion-safety approval")
    cli.add_argument("--check", action="store_true", help="check local files only; do not launch anything")
    args = cli.parse_args()
    try:
        command = build_command(args.port, args.orca, dummy_upload_test=args.dummy_upload_test,
                                proxy_port=args.proxy_port, enable_job_controls=args.enable_job_controls,
                                allow_sliced_upload=args.allow_sliced_upload, status_capture=args.status_capture)
    except ValueError as exc:
        cli.error(str(exc))
    if args.proxy_port is not None:
        print(f"PROXY MODE: Save to 127.0.0.1:{args.proxy_port} may reach REAL HARDWARE. No connection until an explicit action.", flush=True)
        print(f"Start/Cancel enabled: {args.enable_job_controls}; generated-output saving: {args.allow_sliced_upload}.", flush=True)
        print("Proxy is not a safety filter. New candidate startup/clearance remains unverified; no automatic start or stop.", flush=True)
    elif args.dummy_upload_test:
        print("DUMMY UPLOAD TEST: a new owned dummy is created; confirmed Start/Cancel are virtual only.", flush=True)
    else:
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
