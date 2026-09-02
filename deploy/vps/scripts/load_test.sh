#!/usr/bin/env bash
set -Eeuo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/.."
set -a; source .env; set +a
python3 scripts/load_test.py "https://${CENTRAL_CTE_DOMAIN}/api/health" --requests "${1:-200}" --concurrency "${2:-10}"
