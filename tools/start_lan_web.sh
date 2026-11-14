#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
# No IP argument needed. Read our own interface configuration, never probe the printer.
HOST="auto"
if [[ $# -gt 0 && "$1" != -* ]]; then
    HOST="$1"
    shift
fi
# Explicit full-workflow sharing requested by the operator. Never a new target/profile guess.
# A LAN password is mandatory and generated per run. HTTP has no encryption.
exec python3 "$ROOT/tools/start_offline_web.py" --proxy-port 9000 --enable-job-controls --allow-sliced-upload --lan-host "$HOST" "$@"
