#!/usr/bin/env bash
set -Eeuo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"
cd "$DEPLOY_DIR"

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker não encontrado. Execute primeiro: sudo bash scripts/install_docker_ubuntu.sh"
  exit 2
fi
if ! docker compose version >/dev/null 2>&1; then
  echo "Docker Compose plugin não encontrado."
  exit 3
fi
if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "Arquivo deploy/vps/.env criado. Edite o domínio, e-mail e token antes de continuar."
  exit 4
fi

set -a
# shellcheck disable=SC1091
source .env
set +a

DOMAIN="${CENTRAL_CTE_DOMAIN:-}"
EMAIL="${LETSENCRYPT_EMAIL:-}"
TOKEN="${CENTRAL_CTE_METRICS_TOKEN:-}"
if [[ -z "$DOMAIN" || "$DOMAIN" == "central.seudominio.com.br" || "$DOMAIN" == http* ]]; then
  echo "Defina CENTRAL_CTE_DOMAIN no .env somente com o host, sem http:// ou https://."
  exit 5
fi
if [[ -z "$EMAIL" || "$EMAIL" != *@* ]]; then
  echo "Defina LETSENCRYPT_EMAIL no .env."
  exit 6
fi
if [[ ${#TOKEN} -lt 32 || "$TOKEN" == troque-* ]]; then
  echo "Gere um CENTRAL_CTE_METRICS_TOKEN forte no .env."
  echo "Exemplo: python3 -c 'import secrets; print(secrets.token_urlsafe(48))'"
  exit 7
fi

bash scripts/preflight.sh

mkdir -p backups logs monitor
chmod 755 logs

echo "Validando a configuração..."
docker compose --env-file .env config >/dev/null

echo "Validando o Caddyfile..."
docker run --rm \
  -e CENTRAL_CTE_DOMAIN="$DOMAIN" \
  -e LETSENCRYPT_EMAIL="$EMAIL" \
  -v "$DEPLOY_DIR/Caddyfile:/etc/caddy/Caddyfile:ro" \
  caddy:2.11.4-alpine caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile

echo "Construindo a aplicação..."
docker compose --env-file .env build --pull app

# Ajusta os diretórios bind para o usuário não-root 10001 dos sidecars.
IMAGE="${CENTRAL_CTE_IMAGE:-central-cte-dacte:r12.13}"
docker run --rm --user root \
  -v "$DEPLOY_DIR/backups:/target-backups" \
  -v "$DEPLOY_DIR/monitor:/target-monitor" \
  -v "$DEPLOY_DIR/logs:/target-logs" \
  "$IMAGE" sh -c 'chown -R 10001:10001 /target-backups /target-monitor && chmod 700 /target-backups /target-monitor && chown -R 0:0 /target-logs && chmod 755 /target-logs'

echo "Iniciando aplicação, backup, monitor e Caddy..."
docker compose --env-file .env up -d --remove-orphans

APP_CONTAINER="$(docker compose --env-file .env ps -q app)"
for attempt in $(seq 1 60); do
  state="$(docker inspect --format='{{.State.Health.Status}}' "$APP_CONTAINER" 2>/dev/null || true)"
  if [[ "$state" == "healthy" ]]; then
    echo "Aplicação saudável."
    break
  fi
  if [[ "$attempt" == "60" ]]; then
    echo "A aplicação não ficou saudável no tempo esperado."
    docker compose --env-file .env logs --tail=200 app
    exit 8
  fi
  sleep 3
done

echo
echo "Implantação iniciada: https://${DOMAIN}"
echo "No primeiro acesso, crie o administrador."
echo "Confira o DNS e libere as portas TCP 80/443 no firewall da VPS/provedor. A porta UDP/443 permanece reservada para outros serviços da VPS."
