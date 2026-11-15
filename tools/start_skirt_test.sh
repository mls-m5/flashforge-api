#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
# Isolated workspace for the standard guarded skirt profile; no hardware target.
# This launcher refuses proxy/hardware mode; optional --dummy-upload-test is virtual only.
exec python3 "$ROOT/tools/start_offline_web.py" --native-skirt-test "$@"
