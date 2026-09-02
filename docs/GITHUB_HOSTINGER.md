# GitHub -> Hostinger VPS

## Regra principal

O Git guarda **código**. A VPS guarda **dados** no volume Docker `/data`. Não misture os dois.

Repositório atual:

```text
https://github.com/henriT35/central-cte-dacte.git
```

## Clonar na Hostinger

```bash
ssh root@IP_DA_VPS
apt update
apt install -y git

git clone https://github.com/henriT35/central-cte-dacte.git /opt/central-cte
cd /opt/central-cte/deploy/vps
bash scripts/install_docker_ubuntu.sh
```

Como o repositório é privado, configure autenticação GitHub segura por chave SSH ou credencial/token no momento do clone. **Nunca grave token dentro do repositório.**

## Sem domínio: IP + porta

Este é o modo atual recomendado enquanto não houver domínio.

```bash
cd /opt/central-cte/deploy/vps
bash scripts/setup_ip_mode.sh IP_DA_VPS 8765
sudo bash scripts/configure_firewall.sh 22
bash scripts/preflight.sh
bash scripts/deploy.sh
```

Acesso:

```text
http://IP_DA_VPS:8765
```

O modo IP usa `compose.ip.yaml`, publica somente a porta escolhida da aplicação e mantém o Caddy desligado.

### Aviso de segurança

O acesso direto por IP usa HTTP, portanto não há criptografia TLS. Use como solução temporária. Assim que houver domínio, migre para HTTPS.

## Com domínio: HTTPS

```bash
cd /opt/central-cte/deploy/vps
cp .env.domain.example .env
nano .env
```

Preencha:

```dotenv
CENTRAL_CTE_DEPLOY_MODE=domain
CENTRAL_CTE_DOMAIN=central.seudominio.com.br
LETSENCRYPT_EMAIL=seu-email@seudominio.com.br
CENTRAL_CTE_ALLOWED_HOSTS=central.seudominio.com.br,app,localhost,127.0.0.1
CENTRAL_CTE_METRICS_TOKEN=TOKEN_FORTE
```

Depois:

```bash
sudo bash scripts/configure_firewall.sh 22 domain
bash scripts/preflight.sh
bash scripts/deploy.sh
```

Nesse modo o Caddy publica 80/443 e a aplicação volta a ficar somente na rede Docker interna.

## Atualizar depois

```bash
cd /opt/central-cte
git pull
cd deploy/vps
bash scripts/update.sh
```

O modo de publicação é lido do `.env` e não precisa ser alterado a cada atualização.

## Nunca commitar

- `deploy/vps/.env`
- backups de `/data`
- banco de usuários/sessões
- arquivos `.sswweb` reais
- PDFs/XMLs/faturas
- credenciais PostgreSQL, AWS/S3 ou tokens
