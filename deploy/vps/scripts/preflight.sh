#!/usr/bin/env bash
set -Eeuo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=deploy_common.sh
source "$SCRIPT_DIR/deploy_common.sh"
load_deploy_env

command -v docker >/dev/null 2>&1 || { echo "Docker ausente."; exit 4; }
docker compose version >/dev/null 2>&1 || { echo "Docker Compose plugin ausente."; exit 5; }
dc config -q

if [[ "$CENTRAL_CTE_DEPLOY_MODE" == "domain" ]]; then
  DOMAIN="${CENTRAL_CTE_DOMAIN:-}"
  [[ -n "$DOMAIN" && "$DOMAIN" != "central.seudominio.com.br" ]] || { echo "Domínio não configurado."; exit 3; }
  echo "Modo: DOMÍNIO + HTTPS"
  echo "Domínio configurado: $DOMAIN"
  if command -v getent >/dev/null 2>&1; then
    echo "Resolução DNS:"
    getent ahosts "$DOMAIN" | head -n 8 || echo "AVISO: domínio ainda não resolveu nesta VPS."
  fi
  PORTS=(80 443)
else
  PORT="${CENTRAL_CTE_PUBLIC_PORT:-8765}"
  [[ "$PORT" =~ ^[0-9]+$ ]] && (( PORT >= 1 && PORT <= 65535 )) || { echo "Porta pública inválida: $PORT"; exit 3; }
  echo "Modo: IP + PORTA (HTTP)"
  echo "URL prevista: $(public_url)"
  echo "AVISO: login e tráfego ficam sem HTTPS neste modo."
  PORTS=("$PORT")
fi

for port in "${PORTS[@]}"; do
  if command -v ss >/dev/null 2>&1 && ss -ltn "sport = :$port" | grep -q LISTEN; then
    echo "AVISO: a porta TCP $port já está ocupada."
  else
    echo "Porta TCP $port disponível."
  fi
done

AVAILABLE_KB="$(df -Pk . | awk 'NR==2 {print $4}')"
if [[ -n "$AVAILABLE_KB" ]] && (( AVAILABLE_KB < 5 * 1024 * 1024 )); then
  echo "AVISO: menos de 5 GB livres no disco."
else
  echo "Espaço em disco: OK."
fi

MEM_KB="$(awk '/MemTotal/ {print $2}' /proc/meminfo 2>/dev/null || echo 0)"
if (( MEM_KB > 0 && MEM_KB < 3500000 )); then
  echo "AVISO: menos de aproximadamente 4 GB de RAM detectados."
else
  echo "Memória: OK."
fi

echo "Pré-verificação concluída."
