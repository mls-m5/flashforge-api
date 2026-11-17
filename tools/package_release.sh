#!/usr/bin/env bash
# Package only a reviewed committed HEAD; excludes private runtime data.
set -euo pipefail
exec python3 "$(dirname -- "${BASH_SOURCE[0]}")/package_release.py" "$@"
