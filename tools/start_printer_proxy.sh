#!/usr/bin/env bash
set -euo pipefail
if [[ $# -eq 0 || "$1" == "--help" || "$1" == "-h" ]]; then
    echo "Usage: $0 PRINTER_IP [proxy options]"
    echo "Loopback listener defaults to port 9000; target defaults to port 8899."
    echo "Example: $0 192.168.0.39"
    echo "Verify that IP yourself. ALL commands are forwarded; this is not a safety filter."
    exit 0
fi
IP="$1"
shift
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
echo "Recording proxy -> $IP. No printer connection until a client connects."
exec python3 -m finderlab proxy --host 127.0.0.1 --port 9000 --target-host "$IP" "$@"
