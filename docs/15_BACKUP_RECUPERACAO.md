# 15 — Backup e Recuperação
Produção persiste em `/data`: segurança, workspaces, estados, QA e tabelas ativas.

Scheduler padrão: diário (86400s), retenção 14, backup no start habilitado. SQLite é copiado via API consistente quando possível; S3 é opcional.

Restore verifica SHA opcional, integridade ZIP, formato `central-cte-backup-v1` e path traversal.

## Recuperação de desastre
Parar escritas → preservar `/data` danificado → validar backup/hash → restaurar em ambiente controlado → subir → validar `/api/ready`, login, Base SSW, catálogo e workspaces → processar lote sentinela → registrar incidente.
