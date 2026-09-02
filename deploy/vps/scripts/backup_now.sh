#!/usr/bin/env bash
set -Eeuo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=deploy_common.sh
source "$SCRIPT_DIR/deploy_common.sh"
load_deploy_env
dc run --rm --no-deps \
  --entrypoint python backup \
  -c "import sys; sys.path.insert(0, '/app/deploy/vps/scripts'); import backup_scheduler; backup_scheduler.create_backup()"
ls -lh "$DEPLOY_DIR"/backups/central_cte_full_*.zip | tail -n 5
