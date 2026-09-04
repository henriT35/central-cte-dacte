## Deploy VPS por IP + porta — 2026-09-02

- Adicionado `CENTRAL_CTE_DEPLOY_MODE=ip|domain`.
- Adicionado `compose.ip.yaml` para publicar `http://IP:8765` sem Caddy.
- Caddy passou a usar profile `domain` e permanece desligado no modo IP.
- `deploy.sh`, `preflight.sh`, `status.sh`, `update.sh`, `smoke_test.sh`, `load_test.sh`, backup e restore agora respeitam o modo configurado.
- `configure_firewall.sh` abre 8765 no modo IP ou 80/443 no modo domínio.
- Novo `setup_ip_mode.sh` cria `.env` com token forte automaticamente.
- Mantido o código comercial R12.13.9 / motor RC26.6 sem alteração.

# Changelog recente

## R12.13.10 — 2026-09-04
- O primeiro usuário de uma instalação nova passa a ser criado automaticamente como **Desenvolvedor**.
- Removido o perfil Administrador do fluxo de bootstrap/primeiro acesso.
- A rota `/api/auth/setup` agora cria o primeiro Desenvolvedor e já inicia a sessão com esse perfil.
- Interface de primeiro acesso atualizada para deixar explícito que o perfil inicial é Desenvolvedor.
- Perfis Administrador existentes continuam válidos; não há promoção ou alteração automática de usuários já cadastrados.
- Motor comercial preservado em RC26.6.

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
