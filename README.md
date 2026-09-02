# Central CT-e / DACTE

Versão de aplicação: **RC27.14 WEB/WINDOWS MVP13 R12.13.9**  
Motor comercial preservado: **RC26.6**

Este repositório é a fonte limpa para **GitHub + VPS**. Dados operacionais, usuários, sessões, PDFs, XMLs, faturas, relatórios, backups e arquivos `.sswweb` reais não fazem parte do Git.

> **Use um repositório GitHub PRIVADO.** As tabelas comerciais dos parceiros fazem parte do código/seed de implantação.

## Estrutura principal

- `engine/` — motor e módulos comerciais.
- `web_local/` — aplicação web, serviços, interface e testes.
- `tabelas/` — cadastro consolidado usado pelo motor.
- `deploy/vps/` — Docker, Caddy, backup, monitoramento e scripts de implantação.
- `deploy/vps/seed/partner_tables/` — catálogo oficial de parceiros semeado no volume persistente.
- `bases/` — fica vazio no Git; a Base SSW real é importada depois do deploy.

## Modos de deploy na VPS

### Modo atual: IP + porta, sem domínio

A aplicação pode ser publicada diretamente em:

```text
http://IP_DA_VPS:8765
```

Nesse modo o Caddy fica desligado e a porta 8765 é publicada diretamente pelo Docker.

> Esse modo usa **HTTP sem TLS**. É adequado como solução temporária enquanto não houver domínio. Login e tráfego não ficam criptografados na internet.

### Modo futuro: domínio + HTTPS

Quando houver domínio, basta trocar o modo para `domain`; o mesmo repositório passa a usar Caddy e HTTPS nas portas 80/443, sem expor a 8765.

## Primeiro deploy — Hostinger/VPS por IP

```bash
apt update
apt install -y git

git clone https://github.com/henriT35/central-cte-dacte.git /opt/central-cte
cd /opt/central-cte/deploy/vps

bash scripts/install_docker_ubuntu.sh
```

Configure automaticamente o modo IP:

```bash
bash scripts/setup_ip_mode.sh IP_DA_VPS 8765
```

Se não quiser informar o IP no comando:

```bash
bash scripts/setup_ip_mode.sh
```

Depois:

```bash
sudo bash scripts/configure_firewall.sh 22
bash scripts/preflight.sh
bash scripts/deploy.sh
```

O acesso será mostrado no final do deploy.

## Migrar posteriormente para domínio + HTTPS

```bash
cd /opt/central-cte/deploy/vps
cp .env.domain.example .env
nano .env
```

Preencha domínio, e-mail e um token forte e então:

```bash
sudo bash scripts/configure_firewall.sh 22 domain
bash scripts/preflight.sh
bash scripts/deploy.sh
```

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

O `update.sh` faz backup antes de reconstruir a aplicação e respeita automaticamente o modo `ip` ou `domain` configurado no `.env`.

## Operação

```bash
cd /opt/central-cte/deploy/vps
bash scripts/status.sh
bash scripts/logs.sh
bash scripts/backup_now.sh
bash scripts/smoke_test.sh
```

## Dados persistentes

A produção usa volumes Docker. O principal volume é montado em `/data` e guarda usuários, sessões, workspaces, configurações, documentos e catálogo ativo. **Código Git e dados de produção são separados.**

## Nunca enviar ao Git

O `.gitignore` já cobre, entre outros:

- `.env` e credenciais;
- usuários, sessões e `server_secret.bin`;
- PDFs, XMLs, faturas e relatórios;
- backups;
- arquivos `.sswweb` reais;
- logs, caches, `venv` e `__pycache__`;
- executáveis/runtime Windows.
