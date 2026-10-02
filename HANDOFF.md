# HANDOFF — Central CT-e / DACTE
## SE VOCÊ ESTÁ CONTINUANDO ESTE PROJETO, COMECE AQUI
1. Leia `ESTADO_ATUAL.md` e `docs/00_INDICE_GERAL.md`.
2. Leia `docs/06_REGRAS_NEGOCIO.md` antes de alterar cálculo.
3. RC26.6 é a fonte comercial; não crie fórmula no frontend.
4. Confira `PENDENCIAS.md`.
5. Faça backup de `/data` antes de mudanças estruturais.
6. Rode testes do parceiro/regra afetado e sentinelas.

## Arquivos essenciais
`web_local/server.py`, `security.py`, `developer_tools.py`, `services/engine_xml_service.py`, `engine/central_cte_engine_1_1_36.py`, `engine/central_cte_modular/commercial/`, `web_local/data/partner_tables/`, `deploy/vps/compose.yaml`.

## Decisões invariantes atuais
RC26.6 oficial; PostgreSQL sombra; `.sswweb` oficial; decisão manual preserva automático; produção fora do Git; primeiro bootstrap Desenvolvedor.

## Execução mínima
`python web_local/server.py --host 127.0.0.1 --port 8765`

## Estado
Arquitetura está documentada; pendências principais são higiene de release, exposição pública das tabelas e fechamento da suíte total.
