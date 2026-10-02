# Documentação Mestre — Central CT-e / DACTE

**Versão auditada:** RC27.14 WEB/WINDOWS MVP13 R12.13.10  
**Motor comercial:** RC26.6  
**Data da auditoria:** 2026-10-02

## Comece aqui
1. [Visão geral](01_VISAO_GERAL.md)
2. [Arquitetura](02_ARQUITETURA.md)
3. [Estrutura](03_ESTRUTURA_PROJETO.md)
4. [Tecnologias](04_TECNOLOGIAS.md)
5. [Banco/Persistência](05_BANCO_DADOS.md)
6. [Regras de negócio](06_REGRAS_NEGOCIO.md)
7. [Fluxos](07_FLUXOS.md)
8. [Telas](08_TELAS.md)
9. [API — 82 rotas](09_API.md)
10. [Integrações](10_INTEGRACOES.md)
11. [Autenticação/Permissões](11_AUTENTICACAO_PERMISSOES.md)
12. [Instalação](12_INSTALACAO.md)
13. [Execução](13_EXECUCAO.md)
14. [Deploy/Infra](14_DEPLOY_INFRA.md)
15. [Backup/Recuperação](15_BACKUP_RECUPERACAO.md)
16. [Testes/QA](16_TESTES_QA.md)
17. [Bugs/Riscos](17_BUGS_CONHECIDOS.md)
18. [Pendências](18_PENDENCIAS.md)
19. [ADRs](19_DECISOES_ARQUITETURA.md)
20. [Histórico](20_HISTORICO.md)
21. [Mapa de dependências](21_MAPA_DEPENDENCIAS.md)
22. [Mapa de impacto](22_MAPA_IMPACTO.md)
23. [Segurança](23_SEGURANCA.md)
24. [Glossário](24_GLOSSARIO.md)
25. [FAQ técnico](25_FAQ_TECNICO.md)
26. [Variáveis de ambiente](26_VARIAVEIS_AMBIENTE.md)
27. [Automações/Jobs](27_AUTOMACOES_JOBS.md)
28. [Diagnóstico](28_DIAGNOSTICO.md)
29. [Logs/Observabilidade](29_LOGS_OBSERVABILIDADE.md)
30. [Funcionalidades incompletas](30_FUNCIONALIDADES_INCOMPLETAS.md)
31. [Código legado](31_CODIGO_LEGADO.md)
32. [Inventário](INVENTARIO_ARQUIVOS.md)
33. [Cobertura](COBERTURA_DOCUMENTACAO.md)
34. [Informações adicionais](INFORMACOES_ADICIONAIS.md)
35. [Estado atual](../ESTADO_ATUAL.md)
36. [Handoff](../HANDOFF.md)
37. [Pendências canônicas](../PENDENCIAS.md)
38. [Changelog](../CHANGELOG.md)

## Situação resumida
- RC26.6 continua a fonte oficial de cálculo; nenhuma regra comercial foi alterada nesta documentação.
- 611 arquivos originais foram inventariados via manifesto SHA; 222 Python próprios compilam sem erro.
- 207 testes foram coletados; bateria crítica: 65 pass / 2 falhas de expectativa de versão; suíte total não concluiu na janela da auditoria.
- Base SSW `.sswweb` é oficial; PostgreSQL permanece sombra/read-only.
- Primeiro usuário de instalação vazia é Desenvolvedor.
- Repo é público e contém tabelas comerciais versionadas: risco organizacional a validar.
- ZIP auditado contém runtime de segurança local ignorado pelo Git; esse diretório não foi encontrado no repo público.

## Prioridade imediata
Higienizar release ZIP → validar exposição pública das tabelas → corrigir testes/hashes/strings de versão → rodar suíte completa → validar deploy/restore externo.

## Níveis de confiança
Use: **CONFIRMADO PELO CÓDIGO**, **CONFIRMADO POR TESTE**, **CONFIRMADO POR DOCUMENTAÇÃO**, **INFERIDO**, **NÃO CONFIRMADO**. Suposições não devem ser promovidas a fato.
