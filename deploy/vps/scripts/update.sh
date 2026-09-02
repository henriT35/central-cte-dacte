#!/usr/bin/env bash
set -Eeuo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=deploy_common.sh
source "$SCRIPT_DIR/deploy_common.sh"
load_deploy_env

echo "Criando backup antes da atualização..."
dc run --rm --no-deps \
  --entrypoint python backup \
  -c "import sys; sys.path.insert(0, '/app/deploy/vps/scripts'); import backup_scheduler; backup_scheduler.create_backup()"

echo "Reconstruindo e atualizando os serviços..."
dc build --pull app
if [[ "$CENTRAL_CTE_DEPLOY_MODE" == "ip" ]]; then
  docker compose --env-file .env -f compose.yaml --profile domain stop caddy >/dev/null 2>&1 || true
fi
dc up -d --remove-orphans

APP_CONTAINER="$(dc ps -q app)"
for attempt in $(seq 1 60); do
  state="$(docker inspect --format='{{.State.Health.Status}}' "$APP_CONTAINER" 2>/dev/null || true)"
  if [[ "$state" == "healthy" ]]; then
    dc ps
    echo "Atualização concluída e aplicação saudável."
    echo "URL: $(public_url)"
    exit 0
  fi
  if [[ "$attempt" == "60" ]]; then
    echo "A atualização não ficou saudável; consulte os logs."
    dc logs --tail=200 app
    exit 8
  fi
  sleep 3
done
