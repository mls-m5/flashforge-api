#!/usr/bin/env bash
# Full local checks; --python-only explicitly skips Node/UI checks.
set -euo pipefail
exec python3 "$(dirname -- "${BASH_SOURCE[0]}")/check.py" "$@"
