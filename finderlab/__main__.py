"""Run with python3 -m finderlab mock; no installation required."""

import argparse
import asyncio
import logging

from .simulator import MockConfig, MockPrinter
from .simulator.profile import PROFILE_ID


def parser() -> argparse.ArgumentParser:
    cli = argparse.ArgumentParser(
        prog="python3 -m finderlab", description="Finder 2 offline protocol lab",
    )
    commands = cli.add_subparsers(dest="command", required=True)
    mock = commands.add_parser("mock", help="run the synthetic, memory-only TCP printer")
    defaults = MockConfig()
    mock.add_argument("--host", default=defaults.host, help="bind address (default: loopback)")
    mock.add_argument("--port", type=int, default=defaults.port, help="TCP port (default: 8899; 0 selects a free port)")
    mock.add_argument("--idle-timeout", type=float, default=defaults.idle_timeout, help="idle/read/write timeout in seconds")
    for name in ("max_file_size", "storage_limit", "max_files", "max_clients", "max_command_size"):
        mock.add_argument("--" + name.replace("_", "-"), type=int, default=getattr(defaults, name))
    mock.add_argument("--verbose", action="store_true", help="log commands (may expose filenames)")
    return cli


async def run(config: MockConfig):
    async with MockPrinter(config) as printer:
        host, port = printer.address
        print(f"Synthetic printer ({PROFILE_ID}) listening on {host}:{port}", flush=True)
        print("Not verified against Finder 2 or FlashPrint. No discovery; files are RAM-only.", flush=True)
        await asyncio.Future()


def main():
    cli = parser()
    args = vars(cli.parse_args())
    args.pop("command")
    verbose = args.pop("verbose")
    try:
        config = MockConfig(**args)
    except ValueError as exc:
        cli.error(str(exc))
    logging.basicConfig(
        level=logging.INFO if verbose else logging.WARNING,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    try:
        asyncio.run(run(config))
    except KeyboardInterrupt:
        pass
    except OSError as exc:
        cli.exit(1, f"Cannot run mock: {exc}\n")


if __name__ == "__main__":
    main()
