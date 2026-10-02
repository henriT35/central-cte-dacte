# ESTADO ATUAL — Central CT-e / DACTE
**Atualização:** 2026-10-02  
**Aplicação:** RC27.14 WEB/WINDOWS MVP13 R12.13.10  
**Motor:** RC26.6

## Funciona pelo código/testes disponíveis
Bootstrap Desenvolvedor; autenticação/sessão/CSRF/workspaces; serviços XML/fatura/DACTE/assinatura/relatório; Base/Parceiros por capability; PostgreSQL sombra; deploy Docker; backup/restore/monitor; 222 Python próprios compilam.

## Parcialmente validado
207 testes coletados; bateria crítica 65 pass/2 falhas de versão; suíte total não concluiu em 150s. VPS/HTTPS/restore real não foram reproduzidos nesta auditoria.

## Inconsistências abertas
2 testes R12.13.9; 8 hashes divergentes; textos secundários de versão antigos; ZIP com runtime de segurança local.

## Riscos
Repo público com tabelas comerciais; IP mode sem TLS; ACL retry/discard pode excluir Desenvolvedor.

## Última tarefa
Auditoria/documentação mestre. Nenhuma regra do RC26.6 alterada.

## Próxima ação
Higienizar release ZIP → decidir exposição das tabelas → corrigir testes/hashes/strings → rodar 207 testes completos → validar deploy/restore.
