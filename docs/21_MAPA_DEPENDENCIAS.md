# 21 — Mapa de Dependências
```text
static/index.html + app.js
└── web_local/server.py
    ├── security.AuthManager
    ├── developer_tools.DeveloperTools
    ├── OfficialXmlEngineService -> engine RC26.6 -> Base SSW + tabelas
    ├── OfficialInvoiceEngineService -> módulos invoices
    ├── OfficialDacteService -> rendering/state XML
    ├── OfficialSignatureService -> signing + DACTE
    ├── OfficialReportService -> reports XLSX
    └── SswPostgresService -> PostgreSQL/ponte PowerShell
```
Mudança no motor/tabelas pode repercutir em XML, PDFs, faturas e relatórios.
