# 03 — Estrutura do Projeto
O manifesto original lista **610 entradas** mais o próprio `SHA256SUMS.txt`: 611 arquivos no pacote. Foram identificados **222 Python próprios**, **268 arquivos de vendor** e **33 arquivos de teste**.

```text
central-cte-dacte/
├── engine/                    # motor e modularização
├── web_local/                 # servidor, segurança, serviços, UI e testes
│   ├── services/
│   ├── static/
│   ├── tests/
│   ├── tools/
│   └── vendor/
├── deploy/vps/                # Docker/Caddy/scripts
├── tabelas/                   # cadastro mestre comercial
├── fontes/                    # fontes documentais/tabelas
├── bases/                     # sem Base SSW real no Git
└── docs/
```

## Legado
`engine/legacy/`, `central_cte_modular/legacy_core/` e patches RC históricos são **LEGADO / COMPATIBILIDADE**, não lixo. Remoção exige análise de referências e regressão.

## Inventário total
Ver `INVENTARIO_ARQUIVOS.csv`, com todos os arquivos do manifesto classificados.
