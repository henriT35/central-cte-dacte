# 01 — Visão Geral
**Projeto:** Central CT-e / DACTE  
**Aplicação:** RC27.14 WEB/WINDOWS MVP13 R12.13.10  
**Motor comercial:** RC26.6

## Objetivo
Centralizar validação de CT-es de parceiros contra Base SSW e tabelas comerciais, processar faturas, gerar DACTE/PDF, assinatura visual e relatórios, mantendo rastreabilidade e isolamento por usuário.

## Estado atual
Manutenção/homologação avançada. Há execução Windows local, túnel Cloudflare temporário, deploy VPS por IP:porta e arquitetura por domínio+HTTPS. A homologação completa externa não foi repetida nesta auditoria.

## Usuários
- Desenvolvedor: governança completa e recursos técnicos.
- Administrador: operações elevadas específicas.
- Operador: operação diária.
- Consulta: leitura; QA continua permitido.

## Escopo confirmado
XML, faturas PDF, Base SSW `.sswweb`, tabelas de parceiros, DACTE, assinatura visual, relatórios XLSX, QA, backup/restore, jobs, métricas e PostgreSQL sombra.

## Fora do escopo confirmado
ICP-Brasil, promoção automática do PostgreSQL para Base SSW, OpenAI/IA no código atual e sistema bancário/pagamentos completo.

## Próxima versão
NÃO CONFIRMADA pelo código; a prioridade atual está em `PENDENCIAS.md`.
