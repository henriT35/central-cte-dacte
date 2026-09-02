# Central CT-e / DACTE

Versão de aplicação: **RC27.14 WEB/WINDOWS MVP13 R12.13.9**  
Motor comercial preservado: **RC26.6**

Este repositório é a fonte limpa para GitHub + VPS. Dados operacionais, usuários, sessões, PDFs, XMLs, faturas, relatórios, backups e arquivos `.sswweb` reais não fazem parte do Git.

> **Use um repositório GitHub PRIVADO.** As tabelas comerciais dos parceiros fazem parte do código/seed de implantação e não devem ser expostas publicamente.

## Estrutura principal

- `engine/` — motor e módulos comerciais.
- `web_local/` — aplicação web, serviços, interface e testes.
- `tabelas/` — cadastro consolidado usado pelo motor.
- `deploy/vps/` — Docker, Caddy, backup, monitoramento e scripts de implantação.
- `deploy/vps/seed/partner_tables/` — catálogo oficial de parceiros que é semeado no volume persistente.
- `bases/` — fica vazio no Git; a Base SSW real é importada depois do deploy.

## O que NÃO deve ir para o Git

- `.env` e credenciais;
- usuários/senhas/sessões/`server_secret.bin`;
- PDFs, XMLs, faturas e relatórios gerados;
- backups;
- arquivos `.sswweb` reais;
- logs e caches;
- executáveis e runtime Windows.

O `.gitignore` já cobre esses itens.

## Primeiro deploy em VPS Ubuntu/Hostinger

### 1. Clonar o repositório

```bash
sudo mkdir -p /opt/central-cte
sudo chown "$USER":"$USER" /opt/central-cte
git clone SEU_REPOSITORIO_GITHUB /opt/central-cte
cd /opt/central-cte/deploy/vps
```

### 2. Instalar Docker

```bash
sudo bash scripts/install_docker_ubuntu.sh
```

Se o script adicionar seu usuário ao grupo Docker, saia e entre novamente no SSH.

### 3. Criar o `.env`

```bash
cp .env.example .env
nano .env
```

Preencha no mínimo:

```dotenv
CENTRAL_CTE_DOMAIN=central.seudominio.com.br
LETSENCRYPT_EMAIL=seu-email@seudominio.com.br
CENTRAL_CTE_METRICS_TOKEN=COLOQUE_UM_TOKEN_FORTE
```

Para gerar o token:

```bash
python3 -c 'import secrets; print(secrets.token_urlsafe(48))'
```

### 4. Firewall e deploy

Confirme a porta SSH antes de rodar o firewall. Para porta 22:

```bash
sudo bash scripts/configure_firewall.sh 22
bash scripts/preflight.sh
bash scripts/deploy.sh
```

O Caddy publica somente 80/443. A aplicação fica na rede Docker interna na porta 8765.

### 5. Primeiro acesso

No primeiro acesso, crie o usuário Desenvolvedor. Depois importe a **Base SSW `.sswweb` oficial** pela área de Desenvolvedor.

Se houver um backup do volume `/data` da VPS antiga, restaure-o separadamente. **Nunca coloque esse backup no Git.**

## Atualizações futuras via GitHub

No computador de desenvolvimento:

```bash
git add .
git commit -m "descricao da atualizacao"
git push
```

Na VPS:

```bash
cd /opt/central-cte
git pull
cd deploy/vps
bash scripts/update.sh
```

O `update.sh` realiza backup antes de reconstruir a aplicação.

## Operação

```bash
cd /opt/central-cte/deploy/vps
bash scripts/status.sh
bash scripts/logs.sh
bash scripts/backup_now.sh
bash scripts/smoke_test.sh
```

## Dados persistentes

A produção usa volumes Docker. O principal volume é montado em `/data` e guarda usuários, sessões, workspaces, configurações, documentos e catálogo ativo. O código Git e os dados de produção são deliberadamente separados.
