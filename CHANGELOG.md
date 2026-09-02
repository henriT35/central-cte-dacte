# Changelog recente

## R12.13.9 — 2026-09-01
- Corrige geração de prévia/lote assinado para CT-es aprovados manualmente.
- Consolida decisão manual antes do render/assinatura.
- Bloco compacto passa a preservar divergência automática e mostrar `OK MANUAL`, justificativa, responsável e data.
- Launcher local corrige processo antigo preso na porta 8765.

## R12.13.8 — 2026-09-01
- Corrige bloqueio de PDF quando divergência automática já possui baixa manual aprovada.
- Recupera justificativas e decisões manuais persistidas.

## R12.13.7 — 2026-08-31
- AC Log / C Vargas: cálculo oficial usa o maior valor entre percentual da rota, frete-peso e frete mínimo.

## R12.13.6 — 2026-08-31
- Sincronização automática do catálogo de parceiros.
- Corrige falso `PARCEIRO SEM CADASTRO` da Graúna.

## Regras Graúna preservadas
- Redenção/PA normal: 28%.
- Frete mínimo conforme rota.
- Atacadão explícito: regra especial de 40% + autorização.
- Regra acima de 120 kg: somente shadow; não pode gerar falso OK.
