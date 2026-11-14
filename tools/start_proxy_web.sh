#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
# Save is enabled to loopback proxy port 9000; no owned dummy or direct printer IP.
# Active status connects on startup by default; close FlashPrint first (--no-monitor opts out).
# Generated files and job controls require separate explicit flags.
exec python3 "$ROOT/tools/start_offline_web.py" --proxy-port 9000 "$@"
