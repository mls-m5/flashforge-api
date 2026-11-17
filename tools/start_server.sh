#!/usr/bin/env bash
# Start/rebuild this deployment with its existing private configuration.
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
if [[ ! -f .env ]]; then
  printf '%s\n' 'Missing .env. Copy your working server .env here, or copy .env.example.live to .env and set the printer/server IPs.' >&2
  exit 1
fi
exec podman compose up --build -d "$@"
