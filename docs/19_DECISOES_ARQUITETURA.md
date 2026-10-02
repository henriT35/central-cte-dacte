# 19 — Architecture Decision Records
## ADR-001 — RC26.6 é a fonte comercial
UI/serviços delegam ao motor; duplicar fórmula no frontend é proibido. Vigente.

## ADR-002 — workspace por usuário
Uploads/outputs/state isolados; segurança, QA global e catálogo são globais. Vigente.

## ADR-003 — PostgreSQL sombra
Somente leitura/comparação; `.sswweb` continua oficial. Vigente.

## ADR-004 — bootstrap = Desenvolvedor
Primeira conta de instalação vazia é Desenvolvedor. R12.13.10.

## ADR-005 — Git separado de `/data`
Código reprodutível no Git; dados persistentes fora dele. Vigente.

## ADR-006 — IP contingência, domínio produção
IP é simples mas sem TLS; domínio+Caddy é recomendado.

## ADR-007 — legado preservado
Patches/legacy permanecem por compatibilidade até prova por testes de que podem ser removidos.
