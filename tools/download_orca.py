#!/usr/bin/env python3
"""Download a pinned official Linux AppImage; never execute it or install packages."""

import argparse
import hashlib
import math
from pathlib import Path
import platform
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
# 2.5.0: published GitHub asset digest. 2.3.0: hash of the previously
# recorded official download (no upstream digest was published for that asset).
RELEASES = {
    "2.3.0": ("OrcaSlicer_Linux_AppImage_V2.3.0.AppImage", 112784576,
              "73079d88ec36f0615db7919d00aa26fe301e348ba6e051862a7cfc4040150c03"),
    "2.5.0": ("OrcaSlicer_Linux_AppImage_Ubuntu2404_V2.5.0.AppImage", 214571512,
              "d13eb0a9cd618ed080ab6b82c64c0a60c4501aac91e88d5ac2c3b526fb141a7c"),
}


class HTTPSRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if urllib.parse.urlsplit(newurl).scheme != "https":
            raise ValueError("Refusing a non-HTTPS download redirect")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def select_version(requested):
    if platform.system() != "Linux" or platform.machine().lower() not in ("x86_64", "amd64"):
        raise ValueError("This script supports Linux x86_64 only; choose other builds from official releases")
    if requested != "auto":
        return requested
    family, version = platform.libc_ver()
    if family != "glibc":
        raise ValueError("Cannot select a build automatically without glibc; specify --version explicitly")
    try:
        major, minor = map(int, version.split(".")[:2])
    except ValueError as exc:
        raise ValueError("Cannot determine glibc version; specify --version explicitly") from exc
    return "2.5.0" if (major, minor) >= (2, 38) else "2.3.0"


def verify(path, size, expected):
    if path.is_symlink() or not path.is_file() or path.stat().st_size != size:
        raise ValueError(f"Unexpected existing file/type/size: {path}; it was not overwritten")
    digest = hashlib.sha256()
    total = 0
    with path.open("rb") as reader:
        while chunk := reader.read(1024 * 1024):
            total += len(chunk)
            if total > size:
                raise ValueError("File exceeds expected size")
            digest.update(chunk)
    if total != size or digest.hexdigest() != expected:
        raise ValueError(f"SHA-256 mismatch: {path}; it was not overwritten")


def download(version, *, root=ROOT, timeout=300, opener=None):
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("timeout must be positive and finite")
    filename, size, expected = RELEASES[version]
    root = Path(root)
    destination = root / ".local-tools"
    scratch = root / ".tmp"
    destination.mkdir(mode=0o700, parents=True, exist_ok=True)
    scratch.mkdir(mode=0o700, parents=True, exist_ok=True)
    target = destination / filename
    if target.exists() or target.is_symlink():
        verify(target, size, expected)
        target.chmod(0o700)
        return target
    opener = opener or urllib.request.build_opener(HTTPSRedirects())
    url = f"https://github.com/OrcaSlicer/OrcaSlicer/releases/download/v{version}/{filename}"
    request = urllib.request.Request(url, headers={"User-Agent": "finderlab-orca-downloader"})
    deadline = time.monotonic() + timeout
    with tempfile.TemporaryDirectory(prefix="orca-download-", dir=scratch) as directory:
        partial = Path(directory) / "download.AppImage"
        total = 0
        with opener.open(request, timeout=min(30, timeout)) as reader, partial.open("xb") as writer:
            while True:
                if time.monotonic() >= deadline:
                    raise TimeoutError("Download deadline exceeded")
                chunk = reader.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > size:
                    raise ValueError("Download exceeds pinned asset size")
                writer.write(chunk)
        if time.monotonic() >= deadline:
            raise TimeoutError("Download deadline exceeded")
        verify(partial, size, expected)
        partial.chmod(0o700)
        # Both directories are on the project filesystem. Linking publishes the
        # verified file atomically and refuses to replace any concurrent output.
        target.hardlink_to(partial)
    return target


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--version", choices=("auto", *RELEASES), default="auto",
                     help="pinned version (default: auto, based on host glibc)")
    cli.add_argument("--timeout", type=float, default=300, help="download deadline in seconds; socket timeout <=30s")
    args = cli.parse_args()
    try:
        version = select_version(args.version)
        path = download(version, timeout=args.timeout)
    except (OSError, ValueError, urllib.error.URLError) as exc:
        cli.exit(1, f"Cannot download Orca: {exc}\n")
    print(f"OrcaSlicer {version}: {path}")
    print("Size and pinned SHA-256 verified. Nothing was executed or installed system-wide.")
    print("For extraction, runtimes and --orca usage: docs/ORCA_INSTALL.md")


if __name__ == "__main__":
    main()
