# Central CT-e / DACTE — implantação VPS MVP8

Esta pasta deixa a aplicação pronta para uma VPS Linux com Docker Compose. O domínio é configurado no arquivo `.env`; nenhum domínio fica gravado no código.

## Arquitetura

```text
Internet
  ↓ portas 80/443
Caddy 2.11.4 — HTTPS e proxy reverso
  ↓ rede Docker privada
Central CT-e Web :8765
  ├─ volume persistente de dados
  ├─ backup automático local e S3 opcional
  └─ monitor de saúde com webhook opcional
```

A porta 8765 não é publicada no host. Apenas o Caddy recebe tráfego público.

## Pré-requisitos

- VPS Ubuntu ou Debian 64 bits;
- 4 GB de RAM recomendados para processamento e geração de PDF;
- pelo menos 10 GB de disco livre, além do espaço necessário para documentos e backups;
- registro DNS `A` ou `AAAA` do domínio apontando para a VPS;
- portas TCP 80 e 443 liberadas;
- porta UDP 443 opcional para HTTP/3;
- acesso SSH com sudo.

## 1. Enviar o projeto

Copie a pasta completa para a VPS, por exemplo:

```bash
sudo mkdir -p /opt/central-cte
sudo chown "$USER":"$USER" /opt/central-cte
# envie os arquivos para /opt/central-cte
cd /opt/central-cte/deploy/vps
```

## 2. Instalar Docker

```bash
sudo bash scripts/install_docker_ubuntu.sh
```

Depois saia e entre novamente no SSH quando o usuário tiver sido adicionado ao grupo Docker, ou execute os comandos Docker com sudo.

## 3. Configurar firewall

Informe a porta real do SSH. O exemplo abaixo usa 22:

```bash
sudo bash scripts/configure_firewall.sh 22
```

O script preserva primeiro a porta SSH e depois libera TCP 80/443 e UDP 443. Confirme também as regras de firewall do provedor da VPS.

## 4. Configurar domínio e segredos

```bash
cp .env.example .env
nano .env
```

Preencha obrigatoriamente:

```dotenv
CENTRAL_CTE_DOMAIN=central.seudominio.com.br
LETSENCRYPT_EMAIL=seu-email@seudominio.com.br
CENTRAL_CTE_METRICS_TOKEN=um-token-longo-e-aleatorio
```

Gere o token com:

```bash
python3 -c 'import secrets; print(secrets.token_urlsafe(48))'
```

Não use `http://`, `https://` nem barra no domínio. O arquivo `.env` não deve ser enviado para repositório ou compartilhado.

## 5. Pré-verificação e implantação

```bash
bash scripts/preflight.sh
bash scripts/deploy.sh
```

O `deploy.sh` valida o Compose, valida o Caddyfile com a imagem oficial, constrói a aplicação, inicia os serviços e aguarda o healthcheck. Quando DNS e portas estiverem corretos, o Caddy solicita e renova o certificado automaticamente. No primeiro acesso, crie o administrador.

## Operação diária

```bash
bash scripts/status.sh
bash scripts/logs.sh
bash scripts/backup_now.sh
bash scripts/smoke_test.sh
bash scripts/load_test.sh 500 20
```

Atualização de código com backup prévio e espera do healthcheck:

```bash
bash scripts/update.sh
```

## Backup

O serviço `backup` cria um ZIP completo do volume de dados, usa cópia consistente dos bancos SQLite, inclui manifesto e SHA-256 e mantém a quantidade definida em `CENTRAL_CTE_BACKUP_RETENTION_COUNT`.

Arquivos locais:

```text
deploy/vps/backups/
```

Para cópia externa S3 compatível, preencha no `.env`:

```dotenv
S3_BUCKET=meu-bucket
S3_PREFIX=central-cte/producao
S3_ENDPOINT_URL=https://endpoint-do-provedor
S3_REGION=us-east-1
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
S3_SERVER_SIDE_ENCRYPTION=AES256
S3_KMS_KEY_ID=
```

Também é possível usar `S3_SERVER_SIDE_ENCRYPTION=aws:kms` junto com `S3_KMS_KEY_ID`. Com `S3_BUCKET` vazio, o envio externo fica desativado. Os backups locais ficam protegidos por permissões do sistema, mas não são criptografados por senha; trate a pasta como dado confidencial.

### Restauração

1. Faça outro backup dos dados atuais.
2. Coloque o ZIP em `deploy/vps/backups/`.
3. Execute:

```bash
bash scripts/restore.sh backups/central_cte_full_AAAAMMDD_HHMMSS_MICROSSEGUNDOS.zip
```

A restauração exige digitar `RESTAURAR`, verifica o SHA-256 opcional do ZIP, o manifesto e o hash de cada arquivo antes de substituir os dados.

## Monitoramento

O contêiner `monitor` consulta `/api/ready` no intervalo configurado. O último estado fica em:

```text
deploy/vps/monitor/last_status.json
```

Para alertas, informe um webhook que aceite JSON:

```dotenv
ALERT_WEBHOOK_URL=https://seu-servico-de-alerta/exemplo
```

As métricas Prometheus existem em `/api/metrics`, mas o Caddy bloqueia essa rota na internet. Ela permanece disponível apenas na rede Docker e exige o token configurado.

## Segurança aplicada

- HTTPS e renovação automática pelo Caddy;
- limite de 210 MB no corpo recebido pelo proxy;
- aplicação sem porta pública;
- contêiner da aplicação sem root;
- filesystem principal somente leitura;
- capacidades Linux removidas;
- cookie de sessão `Secure`, `HttpOnly` e `SameSite=Strict`;
- sessões persistidas no SQLite por token HMAC, sobrevivendo a reinícios;
- validação de `Host` e confiança no IP encaminhado somente no modo proxy;
- healthcheck e reinício automático;
- volumes separados para dados, cache, certificados e configuração;
- rotação dos logs do Caddy e dos logs dos contêineres;
- backup verificado, retenção e restauração segura;
- firewall configurável sem expor a porta 8765.

## Limite de escala

O MVP8 opera com **uma instância da aplicação**, configuração necessária para preservar filas, locks e o estado de processamento do motor RC26.6. Não aumente o número de réplicas do serviço `app` sem antes migrar esses mecanismos para serviços compartilhados.

## Limites ainda dependentes da VPS real

O pacote foi validado estaticamente e em execução HTTP local, mas este ambiente não possui Docker. Portanto, o build real da imagem, a emissão TLS, o S3, o webhook e o teste de carga com seu lote precisam ser homologados na VPS.
