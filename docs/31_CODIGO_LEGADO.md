# 31 — Código Legado

## Áreas
- `engine/legacy/`;
- `engine/central_cte_modular/legacy_core/`;
- patches/runtime RC históricos e bridges em `bootstrap/`;
- versões anteriores `central_cte_engine_1_1_34.py` e `_35.py` ao lado do entrypoint `_36.py`.

## Função provável/confirmada
Preservar compatibilidade de comportamento durante a modularização e permitir fallback controlado por bridges/flags de ambiente.

## Status
**LEGADO / COMPATIBILIDADE — POSSIVELMENTE AINDA UTILIZADO.** Não excluir por limpeza estética.

## Como avaliar remoção
1. busca de imports/referências/registry/bridges;
2. identificar flag de fallback associada;
3. rodar testes completos e sentinelas comerciais;
4. comparar outputs antes/depois;
5. remover somente em mudança isolada e reversível.
