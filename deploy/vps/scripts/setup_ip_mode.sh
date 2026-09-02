#!/usr/bin/env bash
set -Eeuo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"
cd "$DEPLOY_DIR"

PUBLIC_HOST="${1:-}"
PUBLIC_PORT="${2:-8765}"
ALLOWED_HOSTS="*"
if [[ -n "$PUBLIC_HOST" ]]; then
  ALLOWED_HOSTS="${PUBLIC_HOST},localhost,127.0.0.1,app"
fi
[[ "$PUBLIC_PORT" =~ ^[0-9]+$ ]] && (( PUBLIC_PORT >= 1 && PUBLIC_PORT <= 65535 )) || {
  echo "Porta inválida: $PUBLIC_PORT"; exit 2;
}

if [[ -f .env ]]; then
  cp -p .env ".env.backup.$(date +%Y%m%d_%H%M%S)"
  echo "Backup do .env atual criado."
fi
cp .env.example .env
TOKEN="$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')"

python3 - "$PUBLIC_HOST" "$PUBLIC_PORT" "$TOKEN" "$ALLOWED_HOSTS" <<'PY'
from pathlib import Path
import sys
host, port, token, allowed_hosts = sys.argv[1:]
p = Path('.env')
lines = p.read_text(encoding='utf-8').splitlines()
repl = {
    'CENTRAL_CTE_DEPLOY_MODE': 'ip',
    'CENTRAL_CTE_PUBLIC_PORT': port,
    'CENTRAL_CTE_PUBLIC_HOST': host,
    'CENTRAL_CTE_ALLOWED_HOSTS': allowed_hosts,
    'CENTRAL_CTE_DOMAIN': '',
    'LETSENCRYPT_EMAIL': '',
    'CENTRAL_CTE_METRICS_TOKEN': token,
}
out=[]
seen=set()
for line in lines:
    if '=' in line and not line.lstrip().startswith('#'):
        key=line.split('=',1)[0].strip()
        if key in repl:
            out.append(f'{key}={repl[key]}')
            seen.add(key)
            continue
    out.append(line)
for key,value in repl.items():
    if key not in seen:
        out.append(f'{key}={value}')
p.write_text('\n'.join(out)+'\n', encoding='utf-8')
PY

chmod 600 .env

echo
echo "Modo IP configurado."
echo "Porta pública: $PUBLIC_PORT"
if [[ -n "$PUBLIC_HOST" ]]; then
  echo "URL prevista: http://${PUBLIC_HOST}:${PUBLIC_PORT}"
else
  echo "IP público não informado; o deploy tentará detectar o IP da VPS."
fi
echo "Próximos comandos:"
echo "  sudo bash scripts/configure_firewall.sh 22"
echo "  bash scripts/preflight.sh"
echo "  bash scripts/deploy.sh"
