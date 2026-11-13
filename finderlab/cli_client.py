"""CLI front-end for byte-preserving upload and separately confirmed job actions."""

import asyncio
from dataclasses import asdict
import logging
from pathlib import Path

from .capture import Capture, CaptureError
from .client import ClientConfig, ClientError, FinderClient, remote_path, validate_file

CLIENT_COMMANDS = {"upload", "status", "start", "stop"}


class PreflightError(ValueError):
    """Invalid user input, recorded before any endpoint connection."""


def add_client_commands(commands):
    upload = commands.add_parser("upload", help="send .gx/.gcode/.g; upload-only unless --start is specified")
    upload.add_argument("file", type=Path)
    upload.add_argument("--remote-name", help="optional ASCII .gx/.gcode/.g basename; internal spaces allowed")
    upload.add_argument("--start", action="store_true", help="explicitly start this file ONLY after save confirmation (may heat/move)")
    upload.add_argument("--max-file-size", type=int, default=ClientConfig().max_file_size)
    status = commands.add_parser("status", help="read printer state/temperature/progress")
    start = commands.add_parser("start", help="explicitly start an existing remote .gx/.gcode/.g file (may heat/move)")
    start.add_argument("name", help="remote basename, not a host path")
    start.add_argument("--confirm-start", action="store_true", required=True)
    stop = commands.add_parser("stop", help="explicitly request cancellation; not an emergency stop")
    stop.add_argument("--confirm-stop", action="store_true", required=True)
    for parser in (upload, status, start, stop):
        parser.add_argument("--host", default="127.0.0.1", help="target IP (default: loopback; may itself be a hardware proxy)")
        parser.add_argument("--port", type=int, default=8899)
        parser.add_argument("--timeout", type=float, default=15.0, help="reply/write timeout in seconds")
        parser.add_argument("--connect-timeout", type=float, default=8.0)
        parser.add_argument("--save-timeout", type=float, default=30.0)
        parser.add_argument("--allow-hardware", action="store_true", help="permit a non-loopback target; requires physical supervision")
        parser.add_argument("--capture-dir", default="captures", help="private per-run traffic recordings")
        parser.add_argument("--max-capture-bytes", type=int, default=256 * 1024 * 1024)
        parser.add_argument("--experiment-id")
        parser.add_argument("--verbose", action="store_true")


async def run_client(config, mode, options):
    start_requested = mode == "start" or (mode == "upload" and options.get("start", False))
    metadata = {"operation": mode, "config": asdict(config), "start_requested": start_requested}
    if mode == "upload":
        metadata.update(source_name=options["file"].name, remote_name_requested=options["remote_name"])
    capture = Capture(
        options["capture_dir"], "client", metadata=metadata,
        max_bytes=options["max_capture_bytes"], experiment_id=options["experiment_id"],
    )
    print(f"Target: {config.host}:{config.port}", flush=True)
    print(f"Capture directory: {capture.path.resolve()}", flush=True)
    phase = "preflight"
    try:
        # Record input failures too, but never connect before validation succeeds.
        try:
            if mode == "upload":
                validate_file(options["file"], config.max_file_size)
                remote_path(options["remote_name"] if options["remote_name"] is not None else options["file"].name)
            elif mode == "start":
                remote_path(options["name"])
        except (ValueError, OSError) as exc:
            raise PreflightError(str(exc)) from exc
        phase = "connect"
        async with FinderClient(config, capture=capture) as client:
            capture.manifest.update(model="Flashforge Finder", firmware="V1.5 20170419")
            if mode == "upload":
                last_percent = -1
                def progress(acknowledged, size):
                    nonlocal last_percent
                    percent = 100 * acknowledged // size
                    if percent != last_percent:
                        print(f"\rBlock-acknowledged: {acknowledged}/{size} bytes ({percent}%)", end="", flush=True)
                        last_percent = percent
                phase = "upload"
                if start_requested:
                    print("Upload and start explicitly requested (--start). May heat/move after save; no automatic stop or G-code safety validation.", flush=True)
                else:
                    print("Uploading only: no start or stop command will be sent.", flush=True)
                result = await client.upload(options["file"], remote_name=options["remote_name"], progress=progress)
                capture.manifest["metadata"].update(upload_confirmed=True, remote_path=result.path)
                print(f"\nSave confirmed: {result.path} ({result.size} bytes)", flush=True)
                print(f"Source SHA-256: {result.sha256} (not a remote read-back verification)", flush=True)
                if start_requested:
                    phase = "start_after_upload"
                    await client.start(result.path.removeprefix("0:/user/"), confirm=True)
                    capture.manifest["metadata"]["start_acknowledged"] = True
                    print("Start acknowledged. The printer may now heat/move; supervise it physically.", flush=True)
            elif mode == "status":
                phase = "status"
                for command, lines in (await client.status()).items():
                    print(command + ":")
                    for line in lines:
                        print("  " + line.decode("ascii", "backslashreplace"))
            elif mode == "start":
                phase = "start"
                await client.start(options["name"], confirm=options["confirm_start"])
                capture.manifest["metadata"]["start_acknowledged"] = True
                print("Start acknowledged. The printer may now heat/move; supervise it physically.", flush=True)
            else:
                phase = "stop"
                await client.stop(confirm=options["confirm_stop"])
                print("Stop command acknowledged; this does not guarantee READY, no motion, or cooled heaters. Check the printer physically.", flush=True)
    except BaseException as exc:
        if not capture.failed:
            capture.event("error", phase=phase, error_type=type(exc).__name__, message=str(exc))
        raise
    finally:
        capture.close()
        if capture.failed:
            raise CaptureError(f"Recording incomplete: {capture.path.resolve()}. Do not retry an uncertain operation blindly.")


def client_main(cli, mode, args):
    config_keys = ("host", "port", "timeout", "connect_timeout", "save_timeout", "allow_hardware")
    try:
        config = ClientConfig(**{key: args[key] for key in config_keys},
                              max_file_size=args.get("max_file_size", ClientConfig().max_file_size))
        if args["max_capture_bytes"] <= 0:
            raise ValueError("max-capture-bytes must be positive")
    except (ValueError, OSError) as exc:
        cli.error(str(exc))
    logging.basicConfig(
        level=logging.INFO if args["verbose"] else logging.WARNING,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    try:
        asyncio.run(run_client(config, mode, args))
    except KeyboardInterrupt:
        cli.exit(130, "Cancelled. Remote state may be unknown, especially if --start was requested; no automatic retry or stop was performed.\n")
    except PreflightError as exc:
        cli.exit(2, f"{mode.capitalize()} validation failed: {exc}\n")
    except (ClientError, OSError, ValueError) as exc:
        cli.exit(1, f"{mode.capitalize()} failed: {exc}\n")
