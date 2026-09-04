# Deploy temporário por IP + porta

Enquanto não houver domínio, a Central CT-e pode ser publicada diretamente por HTTP:

```text
http://IP_DA_VPS:8765
```

## Configuração recomendada

```bash
cd /opt/central-cte/deploy/vps
bash scripts/setup_ip_mode.sh IP_DA_VPS 8765
sudo bash scripts/configure_firewall.sh 22
bash scripts/preflight.sh
bash scripts/deploy.sh
```

O script `setup_ip_mode.sh`:

- cria `deploy/vps/.env` a partir do exemplo;
- seleciona `CENTRAL_CTE_DEPLOY_MODE=ip`;
- gera um token interno forte;
- configura a porta pública;
- restringe `Host` ao IP informado quando ele é passado no comando.

No modo IP:

- `compose.ip.yaml` publica a porta 8765;
- `CENTRAL_CTE_HTTPS=0`, permitindo que a sessão funcione por HTTP;
- `CENTRAL_CTE_TRUST_PROXY=0`;
- o Caddy não é iniciado.

## Quando houver domínio

Troque para o arquivo de exemplo de domínio:

```bash
cp .env.domain.example .env
nano .env
sudo bash scripts/configure_firewall.sh 22 domain
bash scripts/deploy.sh
```

O modo `domain` ativa o Caddy e HTTPS, deixando a aplicação novamente sem porta pública direta.


## Primeiro acesso

Em uma instalação nova, ao abrir a Central pela primeira vez, a tela de bootstrap cria a primeira conta automaticamente com o perfil **Desenvolvedor**. Não é mais criado um Administrador como usuário inicial.

## Segurança

HTTP por IP não criptografa login, cookies nem documentos em trânsito. Este perfil deve ser tratado como contingência temporária. Não exponha a porta de métricas e mantenha o repositório privado.
