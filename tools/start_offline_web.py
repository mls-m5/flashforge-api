#!/usr/bin/env python3
"""Start the slicing workbench: offline, owned dummy, or explicitly selected proxy."""

import argparse
import ipaddress
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
PROFILE = ROOT / "local-profiles/finder-offline-02"
SKIRT_PROFILE = ROOT / "local-profiles/finder-offline-03"
ORCA = ROOT / ".local-tools/orca-2.5.0/AppRun"
ARCHIVE_ORCA = ROOT / ".local-tools/OrcaSlicer_Linux_AppImage_Ubuntu2404_V2.5.0.AppImage"
FALLBACK_ORCA = ROOT / ".local-tools/orca-slicer"


def build_command(port=8000, orca=None, *, dummy_upload_test=False, proxy_port=None,
                  enable_job_controls=False, allow_sliced_upload=False, status_capture=None, native_skirt_test=False, monitor=None, lan_host=None, lan_network=None):
    if lan_network is not None and lan_host is None:
        raise ValueError("--lan-network needs --lan-host")
    if lan_host is not None:
        address = ipaddress.ip_address(lan_host)
        subnet = ipaddress.ip_network(lan_network or "192.168.0.0/16", strict=True)
        if (address.version != 4 or subnet.version != 4 or
                not subnet.subnet_of(ipaddress.ip_network("192.168.0.0/16")) or address not in subnet):
            raise ValueError("LAN mode needs this COMPUTER's specific 192.168 address in the allowed private subnet")
    if native_skirt_test and proxy_port is not None:
        raise ValueError("Draft03 native skirt is offline/owned-dummy only in this launcher; changed startup needs separate review")
    if monitor and proxy_port is None and not dummy_upload_test:
        raise ValueError("Active monitoring requires proxy mode or an owned dummy; offline means no printer connection")
    polling = (proxy_port is not None or dummy_upload_test) if monitor is None else monitor
    profile = SKIRT_PROFILE if native_skirt_test else PROFILE
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
    workspace = ("web-data/skirt-dummy-test" if dummy_upload_test else "web-data/skirt-offline-test") if native_skirt_test else (
        "web-data/proxy-test" if proxy_port is not None else "web-data/dummy-upload-test" if dummy_upload_test else "web-data/offline-test")
    command = [sys.executable, "-m", "finderlab", "web", "--listen-host", str(address) if lan_host is not None else "127.0.0.1",
               "--listen-port", str(port), "--data-dir", str(ROOT / workspace), "--orca", str(selected.resolve())]
    if lan_host is not None:
        command += ["--lan", "--lan-network", str(subnet)]
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
    if polling:
        command += ["--auto-monitor"]
    elif proxy_port is not None or dummy_upload_test:
        command += ["--enable-monitor"]  # Manual start remains available after opting out of startup polling.
    for kind in ("machine", "process", "filament"):
        path = profile / (kind + ".json")
        if not path.is_file() or not 0 < path.stat().st_size <= 1024 * 1024:
            raise ValueError("Local experimental profile missing/invalid: " + str(path)
                             + ". Private profiles are not included in a fresh Git clone; see docs/ORCA_FINDER_DRAFT_02.md")
        command += ["--" + kind, str(path)]
    # No arbitrary argument forwarding or direct hardware endpoint selection.
    return command


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--port", type=int, default=8000, help="HTTP port (default: 8000)")
    cli.add_argument("--lan-host", help="explicit COMPUTER interface 192.168 IP; password-protected trusted-LAN sharing, no TLS")
    cli.add_argument("--lan-network", help="optional narrower allowed CIDR within 192.168/16")
    cli.add_argument("--orca", type=Path, help="trusted native Orca executable; relative paths are project-relative")
    cli.add_argument("--native-skirt-test", action="store_true", help="use independent offline draft03 native-skirt profiles; no proxy mode")
    cli.add_argument("--dummy-upload-test", action="store_true", help="own a fresh dummy and permit save-only to it (no hardware endpoint)")
    cli.add_argument("--status-capture", type=Path, help="proxy mode: explicit existing capture run/root; default project captures")
    cli.add_argument("--proxy-port", type=int, help="enable Save to an explicitly chosen local proxy port (may reach hardware)")
    cli.add_argument("--enable-job-controls", action="store_true", help="with --proxy-port: enable separately confirmed Start/Cancel")
    cli.add_argument("--allow-sliced-upload", action="store_true", help="with --proxy-port: explicitly permit generated-output Save; NOT motion-safety approval")
    cli.add_argument("--monitor", action=argparse.BooleanOptionalAction, default=None,
                     help="automatic status polling (default in proxy/owned-dummy modes); --no-monitor leaves it off at startup")
    cli.add_argument("--check", action="store_true", help="check local files only; do not launch anything")
    args = cli.parse_args()
    try:
        command = build_command(args.port, args.orca, dummy_upload_test=args.dummy_upload_test,
                                proxy_port=args.proxy_port, enable_job_controls=args.enable_job_controls,
                                allow_sliced_upload=args.allow_sliced_upload, status_capture=args.status_capture,
                                native_skirt_test=args.native_skirt_test, monitor=args.monitor,
                                lan_host=args.lan_host, lan_network=args.lan_network)
    except ValueError as exc:
        cli.error(str(exc))
    if args.proxy_port is not None:
        print(f"PROXY MODE: Save to 127.0.0.1:{args.proxy_port} may reach REAL HARDWARE.", flush=True)
        print("ACTIVE STATUS CONNECTS ON STARTUP; close FlashPrint/other clients first." if "--auto-monitor" in command else "Automatic status connection disabled; manual polling remains available.", flush=True)
        print(f"Start/Cancel enabled: {args.enable_job_controls}; generated-output saving: {args.allow_sliced_upload}.", flush=True)
        print("Proxy is not a safety filter. New candidate startup/clearance remains unverified; no automatic start or stop.", flush=True)
    elif args.dummy_upload_test:
        print("DUMMY UPLOAD TEST: a new owned dummy is created; confirmed Start/Cancel are virtual only.", flush=True)
    else:
        print("OFFLINE SLICING ONLY: printer uploads, Start and Cancel are disabled.", flush=True)
    print(("Draft 03 native skirt" if args.native_skirt_test else "Draft 02") + " is experimental; changed paths are NOT a print approval.", flush=True)
    print("Orca: " + command[command.index("--orca") + 1], flush=True)
    print("Profile/output review used 2.3.0; another build requires new offline output review.", flush=True)
    print("Open http://" + (args.lan_host or "127.0.0.1") + ":" + str(args.port), flush=True)
    if args.lan_host:
        print("LAN SHARING: per-run password printed by server on launch. HTTP is unencrypted; trusted network only. All users share one printer/file slot.", flush=True)
    print("Test cube: " + str(PROFILE / "review/cube-20x20x5.stl"), flush=True)
    if args.check:
        print("Local file checks passed; native runtime libraries are not probed.", flush=True)
        return
    os.chdir(ROOT)
    os.execv(sys.executable, command)


if __name__ == "__main__":
    main()
