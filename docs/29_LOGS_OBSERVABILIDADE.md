# 29 — Logs e Observabilidade

## Onde observar
- stdout/stderr do servidor Python no modo local;
- logs do launcher Windows/Quick Tunnel;
- `docker compose logs` e `deploy/vps/scripts/logs.sh` na VPS;
- `security/audit.jsonl` para autenticação e gestão;
- journals/estados de jobs por workspace;
- `/api/health` e `/api/ready` para saúde;
- `/api/metrics` para métricas Prometheus, protegido por token quando configurado;
- serviço `monitor` consulta readiness e pode disparar webhook.

## Eventos importantes
Login/falha/bloqueio, criação/edição de usuários, import/commit de Base, mudanças em tabelas, decisões manuais, jobs iniciados/concluídos/falhos, backups/restores e sincronizações PostgreSQL devem permanecer rastreáveis.

## Diagnóstico
Nunca registrar senha, token de sessão, credenciais PostgreSQL/S3 ou conteúdo sensível sem necessidade. Para incidentes, correlacione horário, usuário, workspace, job id, endpoint e arquivo de entrada.
