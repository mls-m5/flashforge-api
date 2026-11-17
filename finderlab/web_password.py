"""Salted persistent LAN verifier and offline reset. Never store a password."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import stat

ITERATIONS = 600000
MAX_RECORD_BYTES = 4096


def validate_password(password):
    if not isinstance(password, str) or not 12 <= len(password) <= 128:
        raise ValueError("Use a password of12–128 characters")
    if any(ord(char) < 32 or ord(char) == 127 for char in password):
        raise ValueError("Password must not contain control characters")
    try:
        encoded = password.encode("utf-8")
    except UnicodeError as exc:
        raise ValueError("Password must be valid UTF-8") from exc
    if len(encoded) > 512:
        raise ValueError("Password is too long in UTF-8")
    return encoded


def make_record(password):
    encoded = validate_password(password)
    salt = secrets.token_bytes(32)
    digest = hashlib.pbkdf2_hmac("sha256", encoded, salt, ITERATIONS)
    return {"version": 1, "algorithm": "pbkdf2-sha256", "iterations": ITERATIONS,
            "salt": salt.hex(), "digest": digest.hex()}


def validate_record(record):
    if not isinstance(record, dict) or set(record) != {"version", "algorithm", "iterations", "salt", "digest"}:
        raise ValueError("Invalid LAN password record; use the offline reset tool")
    if (type(record["version"]) is not int or record["version"] != 1
            or record["algorithm"] != "pbkdf2-sha256"
            or type(record["iterations"]) is not int or record["iterations"] != ITERATIONS):
        raise ValueError("Unsupported LAN password record; use the offline reset tool")
    for key in ("salt", "digest"):
        value = record[key]
        if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
            raise ValueError("Invalid LAN password record; use the offline reset tool")
    return record


def verify(record, password):
    try:
        encoded = validate_password(password)
    except ValueError:
        return False
    actual = hashlib.pbkdf2_hmac("sha256", encoded, bytes.fromhex(record["salt"]), record["iterations"])
    return secrets.compare_digest(actual, bytes.fromhex(record["digest"]))


def check_file(path):
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077 or info.st_nlink != 1:
        raise ValueError("LAN password record must be a private0600 regular file (not a link)")
    if not 0 < info.st_size <= MAX_RECORD_BYTES:
        raise ValueError("Invalid LAN password record size; use the offline reset tool")


def load(path):
    check_file(path)
    with path.open("rb") as stream:
        data = stream.read(MAX_RECORD_BYTES + 1)
    if len(data) > MAX_RECORD_BYTES:
        raise ValueError("LAN password record exceeds its bound")
    return validate_record(json.loads(data))


def save(path, record):
    """Atomic replacement under the caller's exclusive workspace lock."""
    if path.exists() or path.is_symlink():
        check_file(path)
    encoded = (json.dumps(validate_record(record), indent=2) + "\n").encode()
    temporary = path.with_name(".auth-" + secrets.token_hex(16) + ".tmp")
    try:
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as output:
            output.write(encoded)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description="Reset persistent LAN login offline; web must be stopped. No printer connection.")
    parser.add_argument("--data-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        import fcntl
        folder = args.data_dir.resolve()
        if not folder.is_dir():
            raise ValueError("Select the existing web data directory")
        with (folder / "workbench.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            password = secrets.token_urlsafe(24)
            save(folder / "auth.json", make_record(password))
        print("Login username: finder")
        print("Login password (reset; share privately): " + password)
    except (OSError, ValueError) as exc:
        parser.exit(1, "Cannot reset login (stop finder-web first): " + str(exc) + "\n")


if __name__ == "__main__":
    main()
