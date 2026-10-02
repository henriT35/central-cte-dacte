# 04 — Tecnologias e Dependências
| Tecnologia | Função | Versão detectada |
|---|---|---|
| Python | motor/backend/scripts | 3.13 no Docker |
| HTTP stdlib | servidor | stdlib |
| SQLite | sessões/cache | stdlib |
| openpyxl | XLSX | 3.1.5 |
| defusedxml | XML endurecido | 0.7.1 |
| Pillow | imagem/assinatura | 12.2.0 |
| WeasyPrint | HTML→PDF | 68.0 |
| reportlab | PDF | 4.4.9 |
| boto3 | backup S3 | 1.43.51 |
| psycopg[binary] | PostgreSQL | 3.2.9 |
| Docker Compose | produção | externo |
| Caddy | TLS/reverse proxy | 2.11.4-alpine |
| Cloudflared | túnel temporário | runtime |
| PowerShell/Bash | automação | SO |

Dependências de produção estão em `deploy/vps/requirements-prod.txt`. O modo local ainda possui `web_local/vendor/`, criando dois caminhos de dependência que precisam permanecer compatíveis.
