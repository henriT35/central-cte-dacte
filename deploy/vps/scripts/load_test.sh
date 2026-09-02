#!/usr/bin/env bash
set -Eeuo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=deploy_common.sh
source "$SCRIPT_DIR/deploy_common.sh"
load_deploy_env
python3 "$DEPLOY_DIR/scripts/load_test.py" "$(public_url)/api/health" --requests "${1:-200}" --concurrency "${2:-10}"
