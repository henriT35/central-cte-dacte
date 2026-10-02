# 02 — Arquitetura
```mermaid
flowchart LR
 U[Usuário] --> F[HTML/CSS/JS]
 F --> S[web_local/server.py]
 S --> A[security.py]
 S --> W[Workspace por usuário]
 S --> X[Serviço XML]
 S --> I[Serviço Faturas]
 S --> D[Serviço DACTE]
 S --> G[Serviço Assinatura]
 S --> R[Serviço Relatórios]
 X --> E[Motor RC26.6]
 I --> E
 D --> E
 G --> E
 R --> E
 E --> B[Base SSW .sswweb]
 E --> T[Tabelas XLSX]
 S --> P[PostgreSQL sombra/read-only]
 S --> DATA[/data]
```

## Frontend
SPA simples em `web_local/static/`; sem React/Vue/Angular.

## Backend
Python stdlib `BaseHTTPRequestHandler` + `ThreadingHTTPServer`. `server.py` roteia API, upload, jobs, bootstrap, arquivos e observabilidade.

## Motor
`engine/central_cte_engine_1_1_36.py` é entrypoint comercial usado pela web; `engine/central_cte_modular/` contém módulos/bridges. Regra central: **a UI não recria fórmulas; RC26.6 é a fonte oficial da decisão comercial**.

## Persistência
`GLOBAL_DATA_ROOT` contém `security/`, `workspaces/<id>/`, `backups/`, `qa/` e `partner_tables/`. Em Docker, é `/data` por volume persistente.

## Concorrência
HTTP é multithread; operações oficiais sensíveis do motor são serializadas por `ENGINE_EXECUTION_LOCK`.
