# 09 — API HTTP

Fonte: `web_local/server.py`. Foram detectadas **82 rotas literais**. POSTs autenticados exigem CSRF, salvo setup/login/ponte PostgreSQL.

| Método | Endpoint | Função | Autenticação |
|---|---|---|---|
| GET | `/api/ready` | saúde/readiness | pública |
| GET | `/api/metrics` | métricas | token de métricas quando configurado |
| GET | `/api/health` | saúde/readiness | pública |
| GET | `/api/auth/status` | autenticação/sessão/senha | pública |
| GET | `/api/bootstrap` | bootstrap da UI | autenticado |
| GET | `/api/xmls` | XML/validação | autenticado |
| GET | `/api/invoices` | faturas | autenticado |
| GET | `/api/partners` | catálogo/tabelas de parceiros | autenticado |
| GET | `/api/reports` | relatórios | autenticado |
| GET | `/api/reports/status` | relatórios | autenticado |
| GET | `/api/dacte/status` | DACTE | autenticado |
| GET | `/api/signatures/status` | assinatura visual/PDF | autenticado |
| GET | `/api/signatures/profiles` | assinatura visual/PDF | autenticado |
| GET | `/api/qa/attachment` | QA/homologação | autenticado |
| GET | `/api/developer/qa/export` | QA/homologação | Desenvolvedor |
| GET | `/api/qa` | QA/homologação | autenticado |
| GET | `/api/settings` | configurações | autenticado |
| GET | `/api/system/health` | saúde/readiness | autenticado |
| GET | `/api/jobs/recovery` | jobs/recuperação | autenticado |
| GET | `/api/admin/backups` | backup/restore | Desenvolvedor |
| GET | `/api/admin/users` | gestão de usuários/sessões | Desenvolvedor |
| GET | `/api/admin/audit` | auditoria | Admin ou Desenvolvedor |
| GET | `/api/developer/features` | feature flags | Desenvolvedor |
| GET | `/api/base/status` | Base SSW | Admin ou Desenvolvedor |
| GET | `/api/developer/postgres/status` | integração PostgreSQL sombra | Desenvolvedor |
| GET | `/api/developer/postgres/bridge-script` | integração PostgreSQL sombra | Desenvolvedor |
| GET | `/api/developer/partners/files` | catálogo/tabelas de parceiros | Desenvolvedor |
| GET | `/api/developer/partners/model` | catálogo/tabelas de parceiros | Desenvolvedor |
| GET | `/api/developer/partners/template` | catálogo/tabelas de parceiros | Desenvolvedor |
| GET | `/api/developer/partners/file` | catálogo/tabelas de parceiros | Desenvolvedor |
| GET | `/api/jobs/` | jobs/recuperação | autenticado |
| GET | `/api/process/xml/status` | XML/validação | autenticado |
| GET | `/api/process/invoices/status` | faturas | autenticado |
| GET | `/api/process/dacte/status` | DACTE | autenticado |
| GET | `/api/process/signatures/status` | assinatura visual/PDF | autenticado |
| GET | `/api/file` | download de arquivo | autenticado |
| POST | `/api/auth/setup` | autenticação/sessão/senha | pública com regra própria |
| POST | `/api/integrations/ssw-postgres/publish` | integração PostgreSQL sombra | Bearer ponte |
| POST | `/api/auth/login` | autenticação/sessão/senha | pública com regra própria |
| POST | `/api/auth/logout` | autenticação/sessão/senha | autenticado + CSRF |
| POST | `/api/auth/password/change` | autenticação/sessão/senha | autenticado + CSRF |
| POST | `/api/developer/postgres/bridge-token/rotate` | integração PostgreSQL sombra | Desenvolvedor |
| POST | `/api/developer/postgres/test` | integração PostgreSQL sombra | Desenvolvedor |
| POST | `/api/developer/postgres/sync-direct` | integração PostgreSQL sombra | Desenvolvedor |
| POST | `/api/developer/postgres/compare` | integração PostgreSQL sombra | Desenvolvedor |
| POST | `/api/admin/users` | gestão de usuários/sessões | Desenvolvedor |
| POST | `/api/admin/users/password` | gestão de usuários/sessões | Desenvolvedor |
| POST | `/api/developer/users/sessions/revoke` | gestão de usuários/sessões | Desenvolvedor |
| POST | `/api/developer/users/update` | gestão de usuários/sessões | Desenvolvedor |
| POST | `/api/developer/users/delete` | gestão de usuários/sessões | Desenvolvedor |
| POST | `/api/admin/backup` | backup/restore | Desenvolvedor |
| POST | `/api/admin/backup/restore` | backup/restore | Desenvolvedor |
| POST | `/api/developer/features` | feature flags | Desenvolvedor |
| POST | `/api/developer/qa/clear` | QA/homologação | Desenvolvedor |
| POST | `/api/base/stage` | Base SSW | Admin ou Desenvolvedor |
| POST | `/api/base/commit` | Base SSW | Admin ou Desenvolvedor |
| POST | `/api/developer/partners/replace` | catálogo/tabelas de parceiros | Desenvolvedor |
| POST | `/api/developer/partners/import` | catálogo/tabelas de parceiros | Desenvolvedor |
| POST | `/api/developer/partners/delete` | catálogo/tabelas de parceiros | Desenvolvedor |
| POST | `/api/jobs/retry` | jobs/recuperação | Admin ou Operador (revisar Dev) |
| POST | `/api/jobs/discard` | jobs/recuperação | Admin ou Operador (revisar Dev) |
| POST | `/api/qa` | QA/homologação | autenticado, inclusive Consulta |
| POST | `/api/upload` | upload controlado | autenticado + CSRF |
| POST | `/api/settings` | configurações | autenticado + CSRF |
| POST | `/api/xml/clear` | XML/validação | autenticado + CSRF |
| POST | `/api/invoices/clear` | faturas | autenticado + CSRF |
| POST | `/api/xml/complementary` | XML/validação | autenticado + CSRF |
| POST | `/api/process/xml/manual-status` | XML/validação | Admin ou Desenvolvedor |
| POST | `/api/process/xml` | XML/validação | autenticado + CSRF |
| POST | `/api/process/invoices` | faturas | autenticado + CSRF |
| POST | `/api/dacte/preview` | DACTE | autenticado + CSRF |
| POST | `/api/dacte/generate-job` | DACTE | autenticado + CSRF |
| POST | `/api/dacte/generate` | DACTE | autenticado + CSRF |
| POST | `/api/signatures/profile` | assinatura visual/PDF | autenticado + CSRF |
| POST | `/api/signatures/profile/delete` | assinatura visual/PDF | autenticado + CSRF |
| POST | `/api/signatures/pdf-images` | assinatura visual/PDF | autenticado + CSRF |
| POST | `/api/signatures/import` | assinatura visual/PDF | autenticado + CSRF |
| POST | `/api/signatures/registration-sheet` | assinatura visual/PDF | autenticado + CSRF |
| POST | `/api/signatures/preview` | assinatura visual/PDF | autenticado + CSRF |
| POST | `/api/signatures/generate-job` | assinatura visual/PDF | autenticado + CSRF |
| POST | `/api/signatures/generate` | assinatura visual/PDF | autenticado + CSRF |
| POST | `/api/reports/generate` | relatórios | autenticado + CSRF |

## Limites de upload
- XML: 20 MB.
- Fatura: 100 MB.
- Base SSW: 200 MB; stage aceita até 220 MB no handler.
- Tabela: 30 MB/40 MB no import de parceiro.
- Restore: 500 MB compactado, 2 GB extraído, 20.000 arquivos.
- QA imagem: 6 MB.

## Contrato
Não há OpenAPI/Swagger detectado. Payloads, validações e códigos de erro detalhados estão nos ramos de `do_GET`/`do_POST`; o código é a fonte de verdade quando documentação antiga divergir.
