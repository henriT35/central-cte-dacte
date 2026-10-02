# 17 — Bugs e Riscos Conhecidos
## BUG-001 — testes históricos fixam R12.13.9
Severidade baixa/média; dois testes falham por string antiga.

## BUG-002 — SHA256SUMS desatualizado
Severidade média; **8 de 610 entradas** divergem: launchers BAT/PS1, criador de Desenvolvedor, ponte PostgreSQL PS1 e dois RECORDs de vendor.

## BUG-003 — strings de versão inconsistentes
`app.js` fallback R12.13.8; launcher local banner MVP10; SERVICE_VERSION de alguns serviços R12.7/R12.13.9; UI possui texto antigo sobre bootstrap via BAT.

## BUG-004 — ZIP inclui runtime de segurança
Severidade alta para distribuição: o ZIP contém `server_secret.bin` e `sessions.sqlite3` locais, embora estejam ignorados pelo Git e não tenham sido encontrados no repo público.

## RISK-005 — repo público expõe tabelas comerciais
README histórico recomendava privado; seed XLSX está versionado. Confirmar autorização/confidencialidade.

## RISK-006 — modo IP é HTTP
Credenciais/documentos trafegam sem TLS.

## RISK-007 — ACL retry/discard
Pode excluir Desenvolvedor; precisa teste/decisão.
