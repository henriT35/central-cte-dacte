#!/usr/bin/env bash
set -Eeuo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=deploy_common.sh
source "$SCRIPT_DIR/deploy_common.sh"
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
  echo "Arquivo deploy/vps/.env criado no modo IP + porta."
  echo "Gere CENTRAL_CTE_METRICS_TOKEN e execute este script novamente."
  exit 4
fi

load_deploy_env
TOKEN="${CENTRAL_CTE_METRICS_TOKEN:-}"
if [[ ${#TOKEN} -lt 32 || "$TOKEN" == troque-* ]]; then
  echo "Gere um CENTRAL_CTE_METRICS_TOKEN forte no .env."
  echo "Exemplo: python3 -c 'import secrets; print(secrets.token_urlsafe(48))'"
  exit 7
fi

if [[ "$CENTRAL_CTE_DEPLOY_MODE" == "domain" ]]; then
  DOMAIN="${CENTRAL_CTE_DOMAIN:-}"
  EMAIL="${LETSENCRYPT_EMAIL:-}"
  if [[ -z "$DOMAIN" || "$DOMAIN" == "central.seudominio.com.br" || "$DOMAIN" == http* ]]; then
    echo "No modo domain, defina CENTRAL_CTE_DOMAIN somente com o host."
    exit 5
  fi
  if [[ -z "$EMAIL" || "$EMAIL" != *@* ]]; then
    echo "No modo domain, defina LETSENCRYPT_EMAIL no .env."
    exit 6
  fi
else
  PORT="${CENTRAL_CTE_PUBLIC_PORT:-8765}"
  if ! [[ "$PORT" =~ ^[0-9]+$ ]] || (( PORT < 1 || PORT > 65535 )); then
    echo "CENTRAL_CTE_PUBLIC_PORT inválida: $PORT"
    exit 5
  fi
fi

bash scripts/preflight.sh

mkdir -p backups logs monitor
chmod 755 logs

echo "Validando a configuração Docker..."
dc config >/dev/null

if [[ "$CENTRAL_CTE_DEPLOY_MODE" == "domain" ]]; then
  echo "Validando o Caddyfile..."
  docker run --rm \
    -e CENTRAL_CTE_DOMAIN="$CENTRAL_CTE_DOMAIN" \
    -e LETSENCRYPT_EMAIL="$LETSENCRYPT_EMAIL" \
    -v "$DEPLOY_DIR/Caddyfile:/etc/caddy/Caddyfile:ro" \
    caddy:2.11.4-alpine caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
else
  # Se esta instalação já usou domínio anteriormente, não deixe Caddy antigo ativo.
  docker compose --env-file .env -f compose.yaml --profile domain stop caddy >/dev/null 2>&1 || true
fi

echo "Construindo a aplicação..."
dc build --pull app

IMAGE="${CENTRAL_CTE_IMAGE:-central-cte-dacte:r12.13.9}"
docker run --rm --user root \
  -v "$DEPLOY_DIR/backups:/target-backups" \
  -v "$DEPLOY_DIR/monitor:/target-monitor" \
  -v "$DEPLOY_DIR/logs:/target-logs" \
  "$IMAGE" sh -c 'chown -R 10001:10001 /target-backups /target-monitor && chmod 700 /target-backups /target-monitor && chown -R 0:0 /target-logs && chmod 755 /target-logs'

echo "Iniciando Central CT-e, backup e monitor..."
dc up -d --remove-orphans

APP_CONTAINER="$(dc ps -q app)"
for attempt in $(seq 1 60); do
  state="$(docker inspect --format='{{.State.Health.Status}}' "$APP_CONTAINER" 2>/dev/null || true)"
  if [[ "$state" == "healthy" ]]; then
    echo "Aplicação saudável."
    break
  fi
  if [[ "$attempt" == "60" ]]; then
    echo "A aplicação não ficou saudável no tempo esperado."
    dc logs --tail=200 app
    exit 8
  fi
  sleep 3
done

echo
if [[ "$CENTRAL_CTE_DEPLOY_MODE" == "ip" ]]; then
  echo "============================================================"
  echo " CENTRAL CT-e ONLINE POR IP + PORTA"
  echo "============================================================"
  echo "Acesso: $(public_url)"
  echo "Protocolo: HTTP (sem TLS). Use este modo como solução temporária."
  echo "Libere TCP ${CENTRAL_CTE_PUBLIC_PORT:-8765} no firewall da VPS e no firewall do provedor."
else
  echo "Implantação iniciada: $(public_url)"
  echo "Confira o DNS e libere TCP 80/443 no firewall da VPS/provedor."
fi
echo "No primeiro acesso, crie o usuário Desenvolvedor."
