# Inventário de Arquivos

## Cobertura
A auditoria percorreu o manifesto `SHA256SUMS.txt`, que contém **610 entradas**, e o próprio manifesto, totalizando **611 arquivos originais**. A lista exata e auditável de caminhos + SHA-256 permanece em [`../SHA256SUMS.txt`](../SHA256SUMS.txt), que é a fonte de inventário arquivo-a-arquivo.

## Classificação por área
| Diretório/arquivo | Função | Importância | Relação | Status |
|---|---|---|---|---|
| `engine/` | motor, domínio, regras, repositories, reports, rendering, signing, validation, XML | ESSENCIAL | RC26.6 e serviços web | ATIVO |
| `engine/legacy/` | compatibilidade histórica | IMPORTANTE | bridges/fallbacks | LEGADO / POSSIVELMENTE AINDA UTILIZADO |
| `engine/central_cte_modular/legacy_core/` | core legado preservado | IMPORTANTE | modularização | LEGADO / COMPATIBILIDADE |
| `web_local/server.py` | servidor HTTP/API/jobs/uploads | ESSENCIAL | frontend + services + data | ATIVO |
| `web_local/security.py` | usuários/sessão/CSRF/auditoria | ESSENCIAL | server + `/data/security` | ATIVO |
| `web_local/developer_tools.py` | capacidades, Base, backup, QA e governança | ESSENCIAL | server/workspaces | ATIVO |
| `web_local/services/` | adaptadores oficiais XML/fatura/DACTE/assinatura/relatório/PostgreSQL | ESSENCIAL | server ↔ engine | ATIVO |
| `web_local/static/` | HTML/CSS/JS/assets | IMPORTANTE | API web | ATIVO |
| `web_local/tests/` | regressão, segurança, contratos e releases | IMPORTANTE | código próprio | TESTE |
| `web_local/tools/` | ferramentas PowerShell auxiliares | IMPORTANTE | PostgreSQL/renderização | ATIVO |
| `web_local/vendor/` | dependências vendorizadas | AUXILIAR | execução local | VENDORIZADO |
| `web_local/data/partner_tables/` | catálogo comercial operacional | ESSENCIAL | motor/serviços | ATIVO |
| `deploy/vps/` | Docker, Caddy, backup, monitor e scripts | IMPORTANTE | infraestrutura | ATIVO |
| `deploy/vps/seed/partner_tables/` | seed comercial do volume | ESSENCIAL | deploy/partner tables | ATIVO |
| `tabelas/` | cadastro mestre consolidado | ESSENCIAL | regras comerciais | ATIVO |
| `fontes/` | fontes/tabelas auxiliares | IMPORTANTE | conferência de regras | ATIVO |
| `bases/` | placeholder da Base SSW; dados reais fora do Git | IMPORTANTE | motor XML | CONFIGURAÇÃO |
| `docs/` e `README*` | documentação e continuidade | IMPORTANTE | projeto | DOCUMENTAÇÃO |
| `.env*`, compose, Dockerfile, Caddyfile | configuração de implantação | IMPORTANTE | VPS/Docker | CONFIGURAÇÃO |
| `.bat`, `.ps1`, `.sh` | inicialização/automação/deploy | IMPORTANTE | Windows/Linux | AUTOMAÇÃO |

## Contagens
- Python total no manifesto: 470.
- Python próprio (vendor excluído): 222.
- Vendor: 268 arquivos.
- Testes em `web_local/tests`: 33 arquivos; 207 casos coletados.
- XLSX: 38 arquivos.

## Regra para arquivo não conhecido
Nenhum arquivo deve ser removido porque “parece inútil”. Se a função específica não for confirmada, classificar como **FUNÇÃO AINDA NÃO CONFIRMADA** e rastrear referências antes de qualquer exclusão.

## Integridade
O inventário de SHA encontrou 8 divergências no pacote auditado; ver `17_BUGS_CONHECIDOS.md` e `INFORMACOES_ADICIONAIS.md`.
