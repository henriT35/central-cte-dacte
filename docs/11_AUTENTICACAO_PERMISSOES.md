# 11 — Autenticação e Permissões
## Senhas e sessão
PBKDF2-HMAC-SHA256, salt aleatório, 310.000 iterações. Sessão de 8h; token é entregue ao navegador e armazenado no SQLite somente por HMAC. Cookie `HttpOnly; SameSite=Strict`, com `Secure` em HTTPS. CSRF por sessão.

Login: bloqueio temporário após 5 falhas em 10 minutos.

## Primeiro acesso
Instalação vazia → primeiro usuário sempre `desenvolvedor`; `setup_admin()` é alias legado e também cria Desenvolvedor.

| Capacidade | Dev | Admin | Operador | Consulta |
|---|:---:|:---:|:---:|:---:|
| Gerenciar usuários | ✓ | — | — | — |
| Base SSW | ✓ | ✓ | — | — |
| Override XML | ✓ | ✓ | — | — |
| Tabelas parceiros | ✓ | — | — | — |
| QA registrar | ✓ | ✓ | ✓ | ✓ |
| QA global/exportar | ✓ | — | — | — |
| Backups/PostgreSQL/features | ✓ | — | — | — |
| Auditoria | ✓ | ✓ | — | — |

**Risco a validar:** `jobs/retry` e `jobs/discard` exigem explicitamente `admin` ou `operador`, podendo excluir Desenvolvedor.
