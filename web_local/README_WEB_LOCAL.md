# Central CT-e / DACTE — Web/Windows MVP13

Esta camada disponibiliza a RC27.14 no navegador, preserva o aplicativo Windows e mantém o motor comercial RC26.6 como única fonte de cálculo e decisão.

## Modo local no Windows

Execute `INICIAR_CENTRAL_CTE_WEB_LOCAL.bat`. O endereço padrão é `http://127.0.0.1:8765`; a porta muda automaticamente quando necessário. No primeiro acesso, crie o usuário Desenvolvedor inicial. Não existe senha padrão no pacote.

## Fluxos conectados

- validação XML oficial RC26.6;
- informação complementar por CT-e, aplicada somente ao DACTE;
- processamento e decisão de faturas;
- limpeza segura dos lotes XML e de faturas;
- relatórios XLSX oficiais;
- prévia e geração de DACTE;
- perfis de assinatura visual;
- lote assinado e PDFs individuais em ZIP.

A interface não possui fórmulas comerciais. Ausência de informação continua aparecendo como `—`, nunca como `R$ 0,00` inventado.

## Segurança e isolamento

- autenticação obrigatória no modo servidor;
- primeiro usuário configurado no navegador como Desenvolvedor;
- senhas com PBKDF2-SHA256, sal aleatório e 310 mil iterações;
- sessões persistentes, opacas e armazenadas pelo hash HMAC do token;
- cookie `HttpOnly` e `SameSite=Strict`; na VPS também `Secure`;
- proteção CSRF nas operações de escrita;
- perfis `desenvolvedor`, `admin`, `operador` e `consulta`;
- isolamento de uploads, estado, relatórios e assinaturas por usuário;
- validação da extensão e do conteúdo dos uploads;
- auditoria em JSONL, readiness e métricas internas.

## Administração de desenvolvimento

- o primeiro perfil `desenvolvedor` é criado somente no computador pelo arquivo `CRIAR_PRIMEIRO_DESENVOLVEDOR.bat`;
- somente Desenvolvedor edita a tabela de parceiros, limpa o caderno de bugs e controla recursos extras;
- Homologação e arquivos técnicos ficam ocultos para perfis comuns, salvo liberação explícita;
- a Base SSW é importada como conjunto completo de arquivos `.sswweb`, com substituição atômica.

## Contrato sentinela

```text
Esperado: R$ 147,45
XML: R$ 149,69
Diferença: R$ 2,24
Status: DIVERGENTE +
```

## Assinatura visual

A assinatura é aplicada somente ao HTML/PDF. O XML fiscal não é alterado. O recurso não cria assinatura digital com certificado ICP-Brasil.

## Implantação VPS

A infraestrutura de produção está em `deploy/vps/` e inclui Docker Compose, Caddy com HTTPS, firewall auxiliar, healthcheck, reinício automático, logs rotativos, backup local/S3, restauração, monitoramento, smoke test e teste de carga. O domínio é informado em `deploy/vps/.env` e não fica gravado no código.

Manual: `deploy/vps/README_VPS.md`.
