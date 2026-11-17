#!/usr/bin/env python3
"""Run flat unittest modules in bounded, isolated processes; no extra dependency."""

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def run_file(root, script, log, env):
    command = [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", script.name, "-v"]
    with log.open("wb") as output:
        result = subprocess.run(command, cwd=root, env=env, stdout=output, stderr=subprocess.STDOUT)
    return result.returncode


def run(root, jobs):
    if not 1 <= jobs <= 8:
        raise ValueError("jobs must be1–8")
    scripts = sorted((root / "tests").glob("test*.py"))
    if not scripts:
        raise ValueError("No Python test files found")
    # The current suite is flat. Fail visibly rather than silently drop future
    # package-based tests until their sharding semantics are implemented.
    nested = set((root / "tests").rglob("test*.py")) - set(scripts)
    if nested:
        raise ValueError("Nested Python tests require serial tools/check.py (no --jobs)")
    scratch = root / ".tmp"
    scratch.mkdir(mode=0o700, exist_ok=True)
    env = {**os.environ, "TMPDIR": str(scratch)}
    failed = []
    with tempfile.TemporaryDirectory(prefix="python-checks-", dir=scratch) as directory:
        logs = Path(directory)
        with ThreadPoolExecutor(max_workers=jobs) as pool:
            futures = {pool.submit(run_file, root, script, logs / script.name, env): script for script in scripts}
            for future in as_completed(futures):
                script = futures[future]
                code = future.result()
                print(f"\n--- {script.name} (exit {code}) ---", flush=True)
                with (logs / script.name).open() as log:
                    shutil.copyfileobj(log, sys.stdout)
                sys.stdout.flush()
                if code:
                    failed.append(script.name)
    if failed:
        print("FAILED Python modules (no retries): " + ", ".join(sorted(failed)), file=sys.stderr)
        return 1
    print(f"All {len(scripts)} Python test files passed ({jobs} isolated processes).", flush=True)
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jobs", type=int, choices=range(1, 9), default=2)
    args = parser.parse_args(argv)
    try:
        return run(ROOT, args.jobs)
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        print(f"Cannot complete parallel Python checks: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
