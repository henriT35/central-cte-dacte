#!/usr/bin/env bash
# Funções comuns dos scripts de deploy. Este arquivo deve ser "source"-ado.

DEPLOY_COMMON_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_DIR="$(cd -- "$DEPLOY_COMMON_DIR/.." && pwd)"

load_deploy_env() {
  cd "$DEPLOY_DIR"
  [[ -f .env ]] || { echo "Arquivo .env ausente. Copie .env.example para .env."; return 2; }
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
  CENTRAL_CTE_DEPLOY_MODE="${CENTRAL_CTE_DEPLOY_MODE:-ip}"
  case "$CENTRAL_CTE_DEPLOY_MODE" in
    ip|domain) ;;
    *) echo "CENTRAL_CTE_DEPLOY_MODE inválido: $CENTRAL_CTE_DEPLOY_MODE (use ip ou domain)."; return 3 ;;
  esac
}

compose_base_args() {
  printf '%s\n' "--env-file" ".env" "-f" "compose.yaml"
  if [[ "${CENTRAL_CTE_DEPLOY_MODE:-ip}" == "ip" ]]; then
    printf '%s\n' "-f" "compose.ip.yaml"
  else
    printf '%s\n' "--profile" "domain"
  fi
}

dc() {
  local args=()
  while IFS= read -r item; do args+=("$item"); done < <(compose_base_args)
  docker compose "${args[@]}" "$@"
}

public_host_guess() {
  if [[ -n "${CENTRAL_CTE_PUBLIC_HOST:-}" ]]; then
    printf '%s' "$CENTRAL_CTE_PUBLIC_HOST"
    return 0
  fi
  local guessed=""
  if command -v ip >/dev/null 2>&1; then
    guessed="$(ip -4 route get 1.1.1.1 2>/dev/null | awk '{for(i=1;i<=NF;i++) if($i=="src") {print $(i+1); exit}}')"
  fi
  if [[ -z "$guessed" ]]; then
    guessed="$(hostname -I 2>/dev/null | awk '{print $1}')"
  fi
  printf '%s' "${guessed:-IP_DA_VPS}"
}

public_url() {
  if [[ "${CENTRAL_CTE_DEPLOY_MODE:-ip}" == "domain" ]]; then
    printf 'https://%s' "${CENTRAL_CTE_DOMAIN:-SEU_DOMINIO}"
  else
    printf 'http://%s:%s' "$(public_host_guess)" "${CENTRAL_CTE_PUBLIC_PORT:-8765}"
  fi
}
