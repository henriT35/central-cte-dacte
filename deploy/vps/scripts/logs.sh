#!/usr/bin/env bash
set -Eeuo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/.."
if [[ $# -gt 0 ]]; then
  docker compose --env-file .env logs -f --tail=200 "$@"
else
  docker compose --env-file .env logs -f --tail=200
fi
