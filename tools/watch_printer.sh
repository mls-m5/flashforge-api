#!/usr/bin/env bash
set -euo pipefail
if [[ $# -gt 1 || "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
    echo "Usage: $0 [WEB_PORT]  (default 8001)"
    echo "Read-only status from existing recordings for the proxy on 127.0.0.1:9000."
    echo "No printer queries, uploads, job controls or slicer are enabled."
    exit 0
fi
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
exec python3 -m finderlab web --listen-port "${1:-8001}" --target-port 9000 \
    --data-dir web-data/status-view --status-capture captures
