# 06 — Regras de Negócio
## Regra-mãe
**RC26.6 é a única fonte oficial de cálculo/decisão comercial.** Web, relatório e PDF não devem criar uma segunda fórmula.

## Catálogo auditado
17 parceiros, 322 regras, 423 regiões, 107 extras, 3 regras de peso especial; tolerância global carregada R$ 1,00.

## AC LOG / C VARGAS
CONFIRMADO POR TESTE: regra híbrida escolhe o maior valor aplicável entre percentual de rota, frete-peso e mínimo. Há matriz de 33 CT-es reais no teste R12.13.7.

## Graúna
CONFIRMADO POR TESTE: Redenção normal preserva 28% + mínimo; Atacadão especial só se aplica ao caso explícito; regra >120 kg deve permanecer shadow quando não homologada como decisão oficial e não pode criar falso OK.

## M&M
CONFIRMADO POR TESTE: São Domingos do Araguaia/São Geraldo do Araguaia usam 35% com mínimo R$70 nos casos de regressão; cotações especiais/autorizadas são separadas e podem exigir autorização manual.

## Decisão manual
Aprovação manual não apaga a fotografia automática. PDF pode exibir `OK MANUAL`, justificativa, responsável e data, preservando status/esperado/diferença do motor.

## Faturas
Arquivos legíveis são processados; duplicatas e rejeitados são persistidos com status/código/motivo; relatório deve listar rejeitados quando houver.

## Sincronização de parceiros
R12.13.6 reconcilia consolidado com XLSX individuais antes do uso do workspace, evitando falso `PARCEIRO SEM CADASTRO` por compilado defasado.

## Status canônicos
`NÃO VALIDADO`, `OK`, `DIVERGENTE`, `REVISÃO NECESSÁRIA`, `BASE NÃO CARREGADA`, `NF NÃO ENCONTRADA`, `PARCEIRO SEM CADASTRO`, `ERRO DE LEITURA`.
