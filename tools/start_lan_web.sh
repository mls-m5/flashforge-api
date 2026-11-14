#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ $# -lt 1 || "$1" == -* ]]; then
    echo "Usage: $0 COMPUTER_192.168_IP [options, e.g. --lan-network 192.168.1.0/24 or --check]" >&2
    echo "Shares Slice, confirmed Save/Start/Cancel and status; proxy target must already be verified." >&2
    exit 2
fi
HOST="$1"
shift
# Explicit full-workflow sharing requested by the operator. Never a new target/profile guess.
# A LAN password is mandatory and generated per run. HTTP has no encryption.
exec python3 "$ROOT/tools/start_offline_web.py" --proxy-port 9000 --enable-job-controls --allow-sliced-upload --lan-host "$HOST" "$@"
