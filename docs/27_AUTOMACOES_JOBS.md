# 27 — Automações e Jobs
- Jobs internos: `xml`, `invoices`, `dacte`, `signature`; possuem progresso/journal e recuperação.
- Backup scheduler: periódico, retenção e S3 opcional.
- Monitor: verifica `/api/ready`, alerta via webhook após limiar de falhas.
- Deploy scripts: instalação Docker, preflight, firewall, deploy, status, logs, backup, restore, smoke/load test e update.
- Launcher Windows: sobe servidor, verifica versão, baixa cloudflared e cria túnel temporário.
- Catálogo de parceiros: sincronizado ao preparar workspace.
- Base SSW: alterada apenas por stage+commit.
