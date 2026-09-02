# Central CT-e / DACTE — implantação VPS

A implantação suporta dois modos com os mesmos contêineres de aplicação, backup e monitoramento.

## Modo IP + porta

```text
Internet
  ↓ HTTP TCP 8765
Central CT-e :8765
  ├─ volume persistente /data
  ├─ backup automático
  └─ monitor de saúde
```

O Caddy fica desativado. A porta é configurável por `CENTRAL_CTE_PUBLIC_PORT`.

## Modo domínio + HTTPS

```text
Internet
  ↓ TCP 80/443
Caddy
  ↓ rede Docker privada
Central CT-e :8765
```

## Instalação rápida por IP

```bash
cd /opt/central-cte/deploy/vps
sudo bash scripts/install_docker_ubuntu.sh
bash scripts/setup_ip_mode.sh IP_DA_VPS 8765
sudo bash scripts/configure_firewall.sh 22
bash scripts/preflight.sh
bash scripts/deploy.sh
```

A URL final será `http://IP_DA_VPS:8765`.

> HTTP por IP não possui TLS. Use temporariamente e migre para domínio + HTTPS quando possível.

## Configuração manual

```bash
cp .env.example .env
nano .env
```

O `.env.example` já vem com:

```dotenv
CENTRAL_CTE_DEPLOY_MODE=ip
CENTRAL_CTE_PUBLIC_PORT=8765
CENTRAL_CTE_BIND_ADDRESS=0.0.0.0
CENTRAL_CTE_ALLOWED_HOSTS=*
```

Gere o token interno:

```bash
python3 -c 'import secrets; print(secrets.token_urlsafe(48))'
```

## Migrar para domínio

```bash
cp .env.domain.example .env
nano .env
sudo bash scripts/configure_firewall.sh 22 domain
bash scripts/deploy.sh
```

## Operação

```bash
bash scripts/status.sh
bash scripts/logs.sh
bash scripts/backup_now.sh
bash scripts/smoke_test.sh
bash scripts/load_test.sh 500 20
bash scripts/update.sh
```

## Backup e restauração

Backups locais ficam em `deploy/vps/backups/`. Para restaurar:

```bash
bash scripts/restore.sh backups/central_cte_full_AAAAMMDD_HHMMSS_MICROSSEGUNDOS.zip
```

O volume `/data` permanece separado do código Git.
