#!/usr/bin/env python3
"""Run local Python/UI/trace checks, never launch configured printers or Orca."""

import argparse
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def node_runtime(env):
    """Fail visibly if full UI checks cannot run; Python-only is explicit."""
    executable = shutil.which("node")
    if executable is None:
        raise ValueError("Full checks need Node.js18+; use --python-only to explicitly skip UI checks")
    result = subprocess.run(
        [executable, "--version"], cwd=ROOT, env=env,
        capture_output=True, text=True, check=True, timeout=10,
    )
    version = re.match(r"^v(\d+)\.", result.stdout.strip())
    if version is None or int(version[1]) < 18:
        raise ValueError("Full checks need Node.js18+; installed node did not report a supported version")
    return executable


def checks(root, node=None, jobs=1):
    """Discover UI checks by filename, not a second manually maintained list."""
    python = [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"]
    if jobs > 1:
        python = [sys.executable, "tools/test_python.py", "--jobs", str(jobs)]
    commands = [("Python unittest suite", python)]
    if node is not None:
        scripts = sorted((root / "tests").glob("test_*.js"))
        if not scripts:
            raise ValueError("No UI test scripts found; refusing to report a full pass")
        for script in scripts:
            commands.append((script.name, [node, str(script.relative_to(root))]))
    commands.append((
        "Reviewed trace integrity", [sys.executable, "tools/export_reviewed_traces.py", "--check"],
    ))
    return commands


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--python-only", action="store_true",
        help="run Python suite and trace integrity only; explicitly skip Node/UI checks",
    )
    parser.add_argument("--jobs", type=int, choices=range(1, 9), default=1,
                        help="Python test processes (1–8, default1); isolate each test file")
    args = parser.parse_args(argv)

    try:
        scratch = ROOT / ".tmp"
        scratch.mkdir(mode=0o700, exist_ok=True)
        env = {**os.environ, "TMPDIR": str(scratch)}
        node = None if args.python_only else node_runtime(env)
        commands = checks(ROOT, node, args.jobs)
        if args.python_only:
            print("Node/UI checks SKIPPED by explicit --python-only request.", flush=True)
        for number, (label, command) in enumerate(commands, start=1):
            print(f"\n[{number}/{len(commands)}] {label}", flush=True)
            result = subprocess.run(command, cwd=ROOT, env=env)
            if result.returncode:
                print(f"FAILED: {label} (exit {result.returncode}); remaining checks were not run.", file=sys.stderr)
                return result.returncode
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        print(f"Cannot complete checks: {exc}", file=sys.stderr)
        return 1

    suffix = "Node/UI checks skipped." if args.python_only else "Python, Node/UI and trace integrity passed."
    print(f"\nCompleted {len(commands)} checks. {suffix}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
