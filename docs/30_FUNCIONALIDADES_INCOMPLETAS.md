# 30 — Funcionalidades Incompletas / Não Confirmadas

## Confirmadas como parciais ou pendentes
- suíte completa de 207 testes não terminou na janela da auditoria;
- homologação real de VPS/DNS/HTTPS e restore completo não foi repetida;
- strings secundárias de versão/primeiro acesso estão defasadas;
- dois testes históricos ainda fixam R12.13.9;
- autorização de `jobs/retry`/`jobs/discard` para Desenvolvedor precisa decisão/teste;
- PostgreSQL é deliberadamente sombra, não substituição da Base SSW.

## TODO/FIXME/pass
A varredura encontrou `pass` principalmente em tratamento defensivo, compatibilidade e fallbacks. Eles **não foram automaticamente classificados como bugs**. Cada ocorrência deve ser avaliada no contexto antes de alteração.

## Regra
Placeholder, mock, rota incompleta ou botão sem ação só deve ser marcado como defeito quando confirmado pelo fluxo/código/teste; não transformar ausência de evidência em fato.
