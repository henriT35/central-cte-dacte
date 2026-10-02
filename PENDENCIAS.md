# Pendências Centrais
## CRÍTICAS
1. Higienizar ZIP: nunca incluir `web_local/data/security/`, sessões/segredos/QA/runtime.
2. Confirmar autorização para tabelas comerciais permanecerem públicas.
3. Não manter IP/HTTP como produção permanente com dados reais.

## IMPORTANTES
1. Atualizar 2 testes fixados em R12.13.9.
2. Regenerar `SHA256SUMS.txt` em checkout limpo.
3. Rodar os 207 testes até conclusão em CI/ambiente dedicado.
4. Revisar ACL `jobs/retry`/`jobs/discard` para Desenvolvedor.
5. Alinhar strings de versão em launcher/app.js/SERVICE_VERSION/UI.

## MELHORIAS
OpenAPI; release automatizada a partir de checkout limpo com secret scan; CI py_compile+pytest+hash; teste automatizado de restore; distinguir versão do serviço interno da versão global.

## DÉBITO TÉCNICO
Bridges/patches legados; persistência híbrida sem migrations; vendor local vs pip Docker.
