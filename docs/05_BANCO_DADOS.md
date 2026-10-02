# 05 — Banco de Dados e Persistência
O projeto usa persistência híbrida; não há um DB relacional principal único.

## SQLite `sessions`
`token_hash` (PK), `user_id`, `username`, `display_name`, `role`, `csrf`, `created_at`, `expires_at`, `last_seen`. Índices em usuário e expiração. WAL habilitado.

## SQLite `xml_parse_cache`
`path` (PK), `size`, `mtime_ns`, `sha256`, `parser_version`, `result_json`, `updated_at`; índice por assinatura do arquivo/parser.

## Arquivos
Usuários: `security/users.json`; exclusões: `deleted_users.json`; auditoria: `audit.jsonl`; workspaces guardam uploads/outputs/state.

## PostgreSQL SSW
Externo e **somente leitura/sombra**. Padrão `staging.stg_ssw_455_fretes`, com snapshot limitado a 300 mil linhas. Não substitui automaticamente `.sswweb`.

## Migrations
Nenhum framework de migrations foi detectado. SQLite usa criação idempotente; futuras mudanças de schema devem prever compatibilidade/migração explícita.
