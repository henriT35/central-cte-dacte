# 14 — Deploy e Infraestrutura
## IP + porta
`compose.yaml + compose.ip.yaml`; publica 8765 e desliga Caddy. HTTP sem TLS: contingência, não produção permanente com dados reais.

## Domínio
Caddy 2.11.4-alpine em 80/443, ACME/TLS, reverse proxy para app privado.

## Hardening
Usuário não-root UID 10001; filesystem read-only; tmpfs; no-new-privileges; capabilities removidas; limites de PIDs/CPU/memória; healthcheck `/api/ready`; rotação de logs.

## Atualização
GitHub guarda código; `/data` guarda produção. Fluxo: `git pull` + `deploy/vps/scripts/update.sh`, com backup antes do rebuild.
