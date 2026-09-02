#!/usr/bin/env bash
set -Eeuo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/.."
[[ -f .env ]] || { echo "Arquivo .env ausente."; exit 2; }
set -a; source .env; set +a

docker compose --env-file .env ps
echo
curl -fsS "https://${CENTRAL_CTE_DOMAIN}/api/ready" | python3 -m json.tool || true
echo
if [[ -f monitor/last_status.json ]]; then
  echo "Último estado do monitor:"
  python3 -m json.tool monitor/last_status.json
fi
