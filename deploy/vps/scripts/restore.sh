#!/usr/bin/env bash
set -Eeuo pipefail
if [[ $# -lt 1 ]]; then
  echo "Uso: $0 backups/central_cte_full_AAAAMMDD_HHMMSS.zip [SHA256]"
  exit 2
fi
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"
cd "$DEPLOY_DIR"
BACKUP="$(realpath "$1")"
EXPECTED="${2:-}"
case "$BACKUP" in
  "$DEPLOY_DIR"/backups/*) ;;
  *) echo "O backup deve estar dentro de deploy/vps/backups."; exit 3;;
esac
[[ -f "$BACKUP" ]] || { echo "Backup não encontrado: $BACKUP"; exit 4; }

echo "ATENÇÃO: os dados atuais serão substituídos por: $BACKUP"
read -r -p "Digite RESTAURAR para continuar: " CONFIRM
[[ "$CONFIRM" == "RESTAURAR" ]] || { echo "Cancelado."; exit 5; }

docker compose --env-file .env stop app backup monitor
ARGS=(python /app/deploy/vps/scripts/restore_backup.py "/backups/$(basename "$BACKUP")" --target /data --confirm)
if [[ -n "$EXPECTED" ]]; then ARGS+=(--expected-sha256 "$EXPECTED"); fi
docker compose --env-file .env run --rm --no-deps --user root \
  -v "$DEPLOY_DIR/backups:/backups:ro" \
  --entrypoint "" app "${ARGS[@]}"
docker compose --env-file .env up -d app backup monitor caddy

echo "Restauração concluída. Execute scripts/status.sh."
