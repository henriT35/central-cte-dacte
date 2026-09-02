#!/usr/bin/env bash
set -Eeuo pipefail

if [[ ${EUID} -ne 0 ]]; then
  echo "Execute como root: sudo bash $0 [PORTA_SSH] [ip|domain] [PORTA_APP]"
  exit 2
fi

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"
if [[ -f "$DEPLOY_DIR/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$DEPLOY_DIR/.env"
  set +a
fi

SSH_PORT="${1:-22}"
MODE="${2:-${CENTRAL_CTE_DEPLOY_MODE:-ip}}"
APP_PORT="${3:-${CENTRAL_CTE_PUBLIC_PORT:-8765}}"

for p in "$SSH_PORT" "$APP_PORT"; do
  [[ "$p" =~ ^[0-9]+$ ]] && (( p >= 1 && p <= 65535 )) || { echo "Porta inválida: $p"; exit 3; }
done
[[ "$MODE" == "ip" || "$MODE" == "domain" ]] || { echo "Modo inválido: $MODE"; exit 4; }

apt-get update
apt-get install -y ufw

ufw allow "${SSH_PORT}/tcp" comment 'SSH'
if [[ "$MODE" == "ip" ]]; then
  ufw allow "${APP_PORT}/tcp" comment 'Central CTe IP direto'
  echo "Modo IP: liberando TCP ${APP_PORT}."
else
  ufw allow 80/tcp comment 'Central CTe HTTP/ACME'
  ufw allow 443/tcp comment 'Central CTe HTTPS'
  ufw allow 443/udp comment 'Central CTe HTTP3'
  echo "Modo domínio: liberando TCP 80/443 e UDP 443."
fi
ufw default deny incoming
ufw default allow outgoing
ufw --force enable
ufw status verbose

echo "Firewall configurado. Confirme também as regras de firewall da Hostinger/provedor."
