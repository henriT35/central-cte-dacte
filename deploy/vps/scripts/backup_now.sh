#!/usr/bin/env bash
set -Eeuo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/.."
[[ -f .env ]] || { echo "Arquivo .env ausente."; exit 2; }
docker compose --env-file .env run --rm --no-deps \
  --entrypoint python backup \
  -c "import sys; sys.path.insert(0, '/app/deploy/vps/scripts'); import backup_scheduler; backup_scheduler.create_backup()"
ls -lh backups/central_cte_full_*.zip | tail -n 5
