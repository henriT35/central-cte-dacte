#!/usr/bin/env bash
set -Eeuo pipefail

if [[ ${EUID} -ne 0 ]]; then
  echo "Execute como root: sudo bash $0 [PORTA_SSH]"
  exit 2
fi

SSH_PORT="${1:-22}"
if ! [[ "$SSH_PORT" =~ ^[0-9]+$ ]] || (( SSH_PORT < 1 || SSH_PORT > 65535 )); then
  echo "Porta SSH inválida: $SSH_PORT"
  exit 3
fi

apt-get update
apt-get install -y ufw

# Primeiro preserva o SSH para evitar perda de acesso.
ufw allow "${SSH_PORT}/tcp" comment 'SSH'
ufw allow 80/tcp comment 'Central CTe HTTP/ACME'
ufw allow 443/tcp comment 'Central CTe HTTPS'
ufw allow 443/udp comment 'Central CTe HTTP3'
ufw default deny incoming
ufw default allow outgoing
ufw --force enable
ufw status verbose

echo "Firewall configurado. Confirme que o provedor também libera TCP 80/443 e, opcionalmente, UDP 443."
