#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
# Separate draft03, not the previously physically tested draft02.
# This launcher refuses proxy/hardware mode; optional --dummy-upload-test is virtual only.
exec python3 "$ROOT/tools/start_offline_web.py" --native-skirt-test "$@"
