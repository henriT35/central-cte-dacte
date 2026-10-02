# Documentação Mestre — Central CT-e / DACTE

**Versão auditada:** RC27.14 WEB/WINDOWS MVP13 R12.13.10  
**Motor comercial:** RC26.6  
**Data desta auditoria documental:** 2026-10-02  
**Estado:** manutenção/homologação com operação local e opção de deploy VPS.

> Regra de continuidade: o código vigente é a fonte de verdade primária. Documentação antiga divergente é preservada e marcada, nunca usada para esconder o comportamento atual.

## Comece aqui

1. [Visão geral](01_VISAO_GERAL.md)
2. [Arquitetura](02_ARQUITETURA.md)
3. [Estrutura e inventário](03_ESTRUTURA_PROJETO.md)
4. [Regras de negócio](06_REGRAS_NEGOCIO.md)
5. [Fluxos](07_FLUXOS.md)
6. [API](09_API.md)
7. [Autenticação e permissões](11_AUTENTICACAO_PERMISSOES.md)
8. [Testes e QA](16_TESTES_QA.md)
9. [Bugs conhecidos](17_BUGS_CONHECIDOS.md)
10. [Segurança](23_SEGURANCA.md)
11. [Variáveis de ambiente](26_VARIAVEIS_AMBIENTE.md)
12. [Automações e jobs](27_AUTOMACOES_JOBS.md)
13. [Diagnóstico](28_DIAGNOSTICO.md)
14. [Estado atual](../ESTADO_ATUAL.md)
15. [Handoff](../HANDOFF.md)
16. [Pendências](../PENDENCIAS.md)
17. [Changelog](../CHANGELOG.md)
18. [Cobertura documental](COBERTURA_DOCUMENTACAO.md)
19. [Inventário completo CSV](INVENTARIO_ARQUIVOS.csv)

## Situação resumida

- O motor oficial permanece **RC26.6**; a camada Web/Windows não deve criar uma segunda fórmula comercial.
- O servidor web é Python `ThreadingHTTPServer`, sem framework web externo.
- Usuários e workspaces são isolados; segurança global fica sob `web_local/data/security` ou `/data/security` em produção.
- Base SSW `.sswweb` continua oficial. PostgreSQL SSW é **sombra/read-only** e não promove dados automaticamente.
- O primeiro usuário de uma instalação vazia é **Desenvolvedor**.
- O repositório GitHub está atualmente **público**. As tabelas comerciais versionadas no seed são, portanto, públicas.
- O pacote ZIP auditado contém arquivos locais ignorados pelo Git (`server_secret.bin`, `sessions.sqlite3`); eles **não foram encontrados no GitHub público**, mas devem ser removidos de futuros pacotes distribuídos.

## Pendências críticas/prioridade imediata

1. Corrigir higiene do pacote ZIP para nunca incluir estado de segurança local.
2. Decidir conscientemente se as tabelas comerciais podem permanecer em repositório público.
3. Atualizar dois testes que ainda fixam literalmente `R12.13.9`.
4. Regenerar `SHA256SUMS.txt`: 8 entradas do pacote não conferem.
5. Executar a suíte completa em ambiente controlado; a auditoria coletou **207 testes**, mas a execução integral excedeu 150 s nesta sessão.

## Nível de confiança

- **CONFIRMADO PELO CÓDIGO:** arquitetura, endpoints, permissões, armazenamento, deploy, regras descritas com referência de teste/código.
- **CONFIRMADO POR TESTE:** compilação dos 222 Python próprios; bateria crítica recente com 65 aprovados e 2 falhas de expectativa de versão.
- **CONFIRMADO POR DOCUMENTAÇÃO:** histórico/release quando não existe evidência executável suficiente.
- **NÃO CONFIRMADO:** homologação completa de VPS real, DNS/HTTPS externo e processamento com Base SSW operacional de produção nesta auditoria.
