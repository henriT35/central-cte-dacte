#!/usr/bin/env bash
set -Eeuo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"
cd "$DEPLOY_DIR"
[[ -f .env ]] || { echo "Arquivo .env ausente."; exit 2; }

echo "Criando backup antes da atualização..."
docker compose --env-file .env run --rm --no-deps \
  --entrypoint python backup \
  -c "import sys; sys.path.insert(0, '/app/deploy/vps/scripts'); import backup_scheduler; backup_scheduler.create_backup()"

echo "Reconstruindo e atualizando os serviços..."
docker compose --env-file .env build --pull app
docker compose --env-file .env up -d --remove-orphans

APP_CONTAINER="$(docker compose --env-file .env ps -q app)"
for attempt in $(seq 1 60); do
  state="$(docker inspect --format='{{.State.Health.Status}}' "$APP_CONTAINER" 2>/dev/null || true)"
  if [[ "$state" == "healthy" ]]; then
    docker compose --env-file .env ps
    echo "Atualização concluída e aplicação saudável."
    exit 0
  fi
  if [[ "$attempt" == "60" ]]; then
    echo "A atualização não ficou saudável; consulte os logs."
    docker compose --env-file .env logs --tail=200 app
    exit 8
  fi
  sleep 3
done
