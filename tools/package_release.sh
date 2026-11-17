#!/usr/bin/env bash
# Keep complete local diagnostics, including failed validation; never retry.
set -euo pipefail
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
umask 077
mkdir -p -- "$ROOT/.tmp/package-logs"
log=$(mktemp "$ROOT/.tmp/package-logs/package-$(date -u +%Y%m%dT%H%M%SZ)-XXXXXX.log")
printf 'Packaging log: %s\n' "$log"
set +e
{
    printf 'Packaging started (UTC): %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    printf 'Source commit: '
    git -C "$ROOT" rev-parse HEAD 2>/dev/null || printf 'unknown\n'
    python3 --version
    python3 "$ROOT/tools/package_release.py" "$@"
} 2>&1 | tee "$log"
statuses=("${PIPESTATUS[@]}")
set -e
status=${statuses[0]}
if (( status == 0 && statuses[1] != 0 )); then
    status=${statuses[1]}
fi
if ! printf 'Exit status: %s\n' "$status" | tee -a "$log"; then
    if (( status == 0 )); then status=1; fi
fi
printf 'Full packaging log saved: %s\n' "$log"
exit "$status"
