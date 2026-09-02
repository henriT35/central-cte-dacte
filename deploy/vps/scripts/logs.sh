#!/usr/bin/env bash
set -Eeuo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=deploy_common.sh
source "$SCRIPT_DIR/deploy_common.sh"
load_deploy_env
if [[ $# -gt 0 ]]; then
  dc logs -f --tail=200 "$@"
else
  dc logs -f --tail=200
fi
