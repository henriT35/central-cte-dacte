#!/usr/bin/env bash
set -Eeuo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=deploy_common.sh
source "$SCRIPT_DIR/deploy_common.sh"
load_deploy_env

dc ps
echo
echo "URL: $(public_url)"
curl -fsS "$(public_url)/api/ready" | python3 -m json.tool || true
echo
if [[ -f "$DEPLOY_DIR/monitor/last_status.json" ]]; then
  echo "Último estado do monitor:"
  python3 -m json.tool "$DEPLOY_DIR/monitor/last_status.json"
fi
