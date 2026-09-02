# Validação — deploy IP + porta — 2026-09-02

Escopo: infraestrutura de VPS/GitHub. O código comercial permanece R12.13.9 / RC26.6.

Validações executadas:

- sintaxe `bash -n` em todos os scripts `.sh` de `deploy/vps/scripts`;
- parse YAML de `compose.yaml` e `compose.ip.yaml`;
- confirmação de `caddy.profiles = [domain]`;
- teste de `setup_ip_mode.sh` com IP e porta fictícios;
- geração automática do token interno;
- cálculo da URL pública `http://IP:8765`;
- smoke HTTP da aplicação ligada em `0.0.0.0` com `CENTRAL_CTE_HTTPS=0`, `TRUST_PROXY=0` e host remoto permitido;
- `/api/health` respondeu `ok=true`, aplicação R12.13.9 e motor RC26.6;
- busca de arquivos sensíveis comuns no pacote limpo: nenhum `.env`, `.pem`, `.p12`, `.pfx`, `server_secret.bin` ou `.sswweb` real;
- remoção física de `__pycache__`, `.pyc` e `.pytest_cache` do pacote de distribuição.

Observação: o ambiente de geração não possui Docker Engine, portanto o build Docker real e a abertura externa da porta devem ser homologados na Hostinger.
