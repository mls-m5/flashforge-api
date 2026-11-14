"""Run lab services, clients and the standalone workbench without installation."""

import argparse
import asyncio
from dataclasses import asdict
import logging

from .capture import Capture, CaptureError
from .cli_client import CLIENT_COMMANDS, add_client_commands, client_main
from .proxy import ProxyConfig, RecordingProxy
from .simulator import MockConfig, MockPrinter
from .simulator.profile import PROFILES
from .web import add_web_command, web_main


def parser() -> argparse.ArgumentParser:
    cli = argparse.ArgumentParser(
        prog="python3 -m finderlab", description="Finder 2 offline protocol lab",
    )
    commands = cli.add_subparsers(dest="command", required=True)
    add_client_commands(commands)
    add_web_command(commands)
    mock = commands.add_parser("mock", help="run the offline TCP dummy printer")
    defaults = MockConfig()
    mock.add_argument("--profile", choices=tuple(PROFILES), default=defaults.profile,
                      help="response profile (default: %(default)s)")
    for name in ("max_file_size", "storage_limit", "max_files", "max_command_size"):
        mock.add_argument("--" + name.replace("_", "-"), type=int, default=getattr(defaults, name))
    proxy = commands.add_parser("proxy", help="record and relay TCP to an explicit printer IP")
    proxy.add_argument("--target-host", required=True, help="explicit target IP address (no scanning)")
    proxy.add_argument("--target-port", type=int, default=8899)
    proxy.add_argument("--connect-timeout", type=float, default=8.0)
    for subcommand, timeout in ((mock, 30.0), (proxy, 60.0)):
        subcommand.add_argument("--host", default="127.0.0.1", help="bind address (default: loopback)")
        subcommand.add_argument("--port", type=int, default=8899, help="TCP port (default: 8899; 0 selects a free port)")
        subcommand.add_argument("--idle-timeout", type=float, default=timeout)
        subcommand.add_argument("--max-clients", type=int, default=8)
        subcommand.add_argument("--verbose", action="store_true", help="also show requests/replies on console")
        subcommand.add_argument("--capture-dir", default="captures", help="parent directory for private per-run recordings")
        subcommand.add_argument("--max-capture-bytes", type=int, default=256 * 1024 * 1024)
        subcommand.add_argument("--max-sessions", type=int, default=1000)
        subcommand.add_argument("--flashprint-version", help="optional experiment metadata")
        subcommand.add_argument("--experiment-id", help="optional experiment metadata")
    return cli


async def run(config, mode, capture_options):
    profile = PROFILES[config.profile] if mode == "mock" else None
    metadata = {"config": asdict(config)}
    if profile:
        metadata.update(profile=profile.id, profile_source_capture=profile.source_capture)
    capture = Capture(
        capture_options["capture_dir"], mode, metadata=metadata,
        max_bytes=capture_options["max_capture_bytes"], max_sessions=capture_options["max_sessions"],
        flashprint_version=capture_options["flashprint_version"],
        experiment_id=capture_options["experiment_id"],
        model="Flashforge Finder (emulated)" if profile else None,
        firmware=profile.firmware if profile else None,
    )
    service = MockPrinter(config, capture=capture) if mode == "mock" else RecordingProxy(config, capture)
    try:
        async with service:
            host, port = service.address
            capture.event("listener_bound", address=[host, port])
            label = f"Dummy printer ({profile.id})" if profile else "Recording proxy"
            print(f"{label} listening on {host}:{port}", flush=True)
            print(f"Capture directory: {capture.path.resolve()}", flush=True)
            if mode == "mock":
                if profile.source_capture:
                    print("Capture-derived replies; name/serial anonymized. Compatibility is limited to observed workflows.", flush=True)
                else:
                    print("Synthetic replies, not verified against Finder 2 or FlashPrint.", flush=True)
                print("No discovery. Upload protocol remains experimental; virtual files are RAM-only.", flush=True)
            else:
                print(f"Target: {config.target_host}:{config.target_port}. Transparent relay: ALL commands are forwarded.", flush=True)
            print("Private raw traffic is saved, including any uploaded files. Stop with Ctrl+C.", flush=True)
            # A capture failure stops the CLI rather than leaving an unusable listener.
            while not capture.failed:
                await asyncio.sleep(0.1)
    except (OSError, ValueError) as exc:
        if not capture.failed:
            capture.event("error", phase="service", error_type=type(exc).__name__, message=str(exc))
        raise
    finally:
        capture.close()
        if capture.failed:
            raise CaptureError(f"Recording is incomplete: {capture.path.resolve()}")


def main():
    cli = parser()
    args = vars(cli.parse_args())
    mode = args.pop("command")
    if mode == "web":
        return web_main(cli, args)
    if mode in CLIENT_COMMANDS:
        return client_main(cli, mode, args)
    verbose = args.pop("verbose")
    capture_options = {key: args.pop(key) for key in (
        "capture_dir", "max_capture_bytes", "max_sessions", "flashprint_version", "experiment_id",
    )}
    try:
        config = MockConfig(**args) if mode == "mock" else ProxyConfig(**args)
        if capture_options["max_capture_bytes"] <= 0 or capture_options["max_sessions"] <= 0:
            raise ValueError("capture limits must be positive")
    except ValueError as exc:
        cli.error(str(exc))
    logging.basicConfig(
        level=logging.INFO if verbose else logging.WARNING,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    try:
        asyncio.run(run(config, mode, capture_options))
    except KeyboardInterrupt:
        pass
    except (OSError, ValueError) as exc:
        cli.exit(1, f"Cannot run {mode}: {exc}\n")


if __name__ == "__main__":
    main()
