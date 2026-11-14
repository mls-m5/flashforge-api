#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
PORT="${1:-8000}"
if [[ $# -gt 1 || ! "$PORT" =~ ^[0-9]{1,5}$ ]]; then
    echo "Usage: $0 [WEB_PORT] (0 selects a fresh ephemeral port)" >&2
    exit 2
fi
PORT=$((10#$PORT))
if (( PORT > 65535 )); then
    echo "Web port must be 0–65535" >&2
    exit 2
fi
cd "$ROOT"
echo "VIRTUAL CONTROL REHEARSAL: owns a fresh dummy; no printer/proxy endpoint is used."
echo "No Orca/profiles needed. Light, XYZ and extruder are counter-only simulations, not wire commands."
exec python3 -m finderlab web --dummy --auto-monitor --listen-port "$PORT" --data-dir "$ROOT/web-data/control-panel-test"
