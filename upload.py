#!/usr/bin/env python3
"""Experimental FlashForge Finder Wi-Fi file uploader (upload only)."""
import argparse
import os
from pathlib import Path
import socket
import sys
import time

PORT = 8899
CHUNK_SIZE = 4096


def read_reply(sock, timeout=8.0):
    """Read the text response up to an 'ok' line or until timeout."""
    sock.settimeout(0.5)
    data = bytearray()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            chunk = sock.recv(4096)
        except socket.timeout:
            continue
        if not chunk:
            raise ConnectionError("Skrivaren stängde anslutningen")
        data.extend(chunk)
        decoded = data.decode("utf-8", "replace")
        if any(line.strip().lower() == "ok" for line in decoded.splitlines()):
            return decoded
        if any(word in decoded.lower() for word in ("error", "failed", "not enough space")):
            return decoded
    return data.decode("utf-8", "replace")


def command(sock, cmd, timeout=8.0):
    print(f"> {cmd}", flush=True)
    sock.sendall((cmd + "\r\n").encode("ascii"))
    reply = read_reply(sock, timeout)
    print(reply.strip() or "(inget svar)", flush=True)
    if not any(line.strip().lower() == "ok" for line in reply.splitlines()):
        raise RuntimeError(f"Saknar bekräftelsen 'ok' efter {cmd}. Avbryter.")


def upload(ip, filename):
    path = Path(filename)
    if not path.is_file():
        raise FileNotFoundError(filename)
    if not path.stat().st_size:
        raise ValueError("Filen är tom")
    if not path.name.isascii() or any(ch.isspace() for ch in path.name):
        raise ValueError("Använd ett filnamn utan mellanslag eller icke-ASCII-tecken")
    size = path.stat().st_size
    remote = f"0:/user/{path.name}"
    print(f"Ansluter till {ip}:{PORT}")
    print(f"Lokal fil: {path} ({size} byte)")
    print(f"Mål: {remote}")

    with socket.create_connection((ip, PORT), timeout=8) as sock:
        command(sock, "~M601 S1")
        try:
            command(sock, f"~M28 {size} {remote}")
            sent = 0
            with path.open("rb") as source:
                while chunk := source.read(CHUNK_SIZE):
                    sock.sendall(chunk)
                    sent += len(chunk)
                    print(f"\rSkickat: {sent}/{size} byte ({100 * sent / size:.1f}%)", end="", flush=True)
            print()
            # Some FlashForge implementations require a pause before M29.
            time.sleep(3)
            command(sock, "~M29", timeout=15)
            print("Överföringen bekräftades av skrivaren. Ingen utskrift har startats.")
        finally:
            try:
                command(sock, "~M602", timeout=3)
            except (OSError, RuntimeError):
                pass


def main():
    parser = argparse.ArgumentParser(description="Ladda upp en fil till FlashForge via Wi-Fi, utan att starta utskrift")
    parser.add_argument("ip", help="Skrivarens IP-adress")
    parser.add_argument("file", help="Fil att överföra, t.ex. modell.gx")
    args = parser.parse_args()
    try:
        upload(args.ip, args.file)
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"Fel: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
