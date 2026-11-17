#!/usr/bin/env python3
"""Package committed source quickly; optionally check it. Never start containers."""

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import sys
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[1]
PREFIX = "finderlab"
MAX_ENTRIES = 10000
MAX_SOURCE_BYTES = 64 * 1024 * 1024
MAX_ARCHIVE_BYTES = 32 * 1024 * 1024
PRIVATE_ROOTS = {
    ".git", ".tmp", ".local-tools", "local-profiles", "captures", "web-data",
    "upload", "uploads", "storage", "dist", "build", ".venv", "venv",
}
PUBLIC_ENV = {".env.example", ".env.example.live"}
REQUIRED = {
    "docker-compose.yml", "compose.live.yml", ".env.example.live",
    "docker/web.Dockerfile", "docker/entrypoint.py", "docker/proxy_health.py",
    "finderlab/web.py", "finderlab/web_password.py", "tools/check.py",
    "tools/test_python.py", "tools/package_release.py", "tools/start_server.sh",
    "docs/DEPLOYMENT.md", "docs/RELEASES.md",
    "profiles/finder2/machine.json", "profiles/finder2/process.json",
    "profiles/finder2/filament.json", "profiles/finder2/LICENSE.txt", "LICENCE",
}


def git(root, *arguments):
    return subprocess.check_output(["git", *arguments], cwd=root).decode("utf-8").strip()


def require_clean(root):
    # Untracked/ignored files are deliberately excluded by git archive. Do not
    # require deleting result.json, models, private config or active recordings.
    result = subprocess.run(["git", "diff", "--quiet", "HEAD", "--"], cwd=root)
    if result.returncode:
        raise ValueError("Commit/review tracked changes before packaging; nothing was archived")


def public_path(name):
    path = PurePosixPath(name)
    if path.is_absolute() or not path.parts or any(part in ("..", ".git", "__pycache__") for part in path.parts):
        return False
    if path.parts[0] in PRIVATE_ROOTS or str(path) == "result.json" or path.name == "auth.json" or path.name.startswith(".auth-"):
        return False
    if path.name.startswith(".env") and str(path) not in PUBLIC_ENV:
        return False
    return path.suffix not in (".pyc", ".pcap", ".pcapng")


def inspect_archive(path):
    if not 0 < path.stat().st_size <= MAX_ARCHIVE_BYTES:
        raise ValueError("Release archive exceeds its byte limit")
    files = set()
    total = 0
    with tarfile.open(path, "r:gz") as archive:
        for count, member in enumerate(archive, start=1):
            parts = PurePosixPath(member.name).parts
            if count > MAX_ENTRIES or not parts or parts[0] != PREFIX:
                raise ValueError("Invalid release prefix/entry count")
            name = "/".join(parts[1:])
            if name and not public_path(name):
                raise ValueError(f"Private/unsafe path cannot be released: {name}")
            if not member.isdir() and not member.isfile():
                raise ValueError("Release must contain regular files/directories only, not links/devices")
            total += member.size
            if total > MAX_SOURCE_BYTES:
                raise ValueError("Release uncompressed bytes exceed limit")
            if member.isfile():
                files.add(name)
    missing = REQUIRED - files
    if missing:
        raise ValueError("Release is missing required source/config/license files: " + ", ".join(sorted(missing)))
    return files, total


def package(root=ROOT, *, check=False, jobs=1):
    root = Path(root).resolve()
    if not 1 <= jobs <= 8 or (jobs != 1 and not check):
        raise ValueError("Use --check with --jobs 1–8; ordinary packaging runs no tests")
    require_clean(root)
    commit = git(root, "rev-parse", "HEAD")
    name = "finderlab-" + commit[:12]
    destination = root / "dist" / "releases" / name
    if destination.exists():
        raise ValueError(f"Release already exists (not overwritten): {destination}")
    tracked = git(root, "ls-tree", "-r", "--name-only", "--full-tree", commit).splitlines()
    if len(tracked) > MAX_ENTRIES or any(not public_path(path) for path in tracked):
        raise ValueError("Tracked tree contains private/unsafe paths or too many entries; review before release")

    objects = git(root, "ls-tree", "-r", "--long", commit).splitlines()
    source_bytes = sum(
        int(size) for row in objects
        if (size := row.split("\t", 1)[0].split()[-1]).isdecimal()
    )
    if source_bytes > MAX_SOURCE_BYTES:
        raise ValueError("Tracked source bytes exceed the release limit")

    scratch = root / ".tmp"
    scratch.mkdir(mode=0o700, exist_ok=True)
    env = {**os.environ, "TMPDIR": str(scratch)}
    command = [sys.executable, "tools/check.py"]
    if jobs != 1:
        command += ["--jobs", str(jobs)]
    if check:
        print("Running Python/UI/trace checks before source packaging…", flush=True)
        subprocess.run(command, cwd=root, env=env, check=True)
    else:
        print("Tests NOT RUN (quick source archive). Use --check for full validation.", flush=True)
    require_clean(root)
    if git(root, "rev-parse", "HEAD") != commit:
        raise ValueError("HEAD changed during checks; run packaging again after reviewing")

    with tempfile.TemporaryDirectory(prefix="release-", dir=scratch) as directory:
        staging = Path(directory)
        archive = staging / (name + ".tar.gz")
        subprocess.run([
            "git", "archive", "--format=tar.gz", "--prefix=" + PREFIX + "/",
            "--output=" + str(archive), commit,
        ], cwd=root, env=env, check=True)
        files, total = inspect_archive(archive)
        checksum = hashlib.sha256(archive.read_bytes()).hexdigest()
        (staging / "SHA256SUMS").write_text(checksum + "  " + archive.name + "\n")
        manifest = {
            "kind": "finderlab-source-release", "commit": commit,
            "tree": git(root, "rev-parse", commit + "^{tree}"),
            "commit_date": git(root, "show", "-s", "--format=%cI", commit),
            "archive": archive.name, "sha256": checksum,
            "files": len(files), "uncompressed_file_bytes": total,
            "checks": {"command": " ".join(["python3", *command[1:]]) if check else None,
                       "result": "passed" if check else "not_run"},
            "container_built": False, "hardware_tested": False,
            "private_runtime_data_included": False,
            "submodule_contents_included": False,
        }
        (staging / "release.json").write_text(json.dumps(manifest, indent=2) + "\n")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.mkdir()  # Refuse concurrent publication/overwrite.
        published = []
        try:
            for filename in (archive.name, "SHA256SUMS", "release.json"):
                target = destination / filename
                target.hardlink_to(staging / filename)
                published.append(target)
        except BaseException:
            for path in reversed(published):
                path.unlink()
            destination.rmdir()
            raise
    print(f"Release: {destination / archive.name}", flush=True)
    print(f"SHA256: {checksum}", flush=True)
    print("Source only; .env/models/captures/local tools excluded. Container builds remain server-side.", flush=True)
    return destination


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="run full Python/UI/trace validation before packaging")
    parser.add_argument("--jobs", type=int, choices=range(1, 9), default=1,
                        help="test processes with --check (default1)")
    args = parser.parse_args(argv)
    try:
        package(check=args.check, jobs=args.jobs)
    except (OSError, ValueError, subprocess.SubprocessError, tarfile.TarError) as exc:
        print("Cannot package release: " + str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
