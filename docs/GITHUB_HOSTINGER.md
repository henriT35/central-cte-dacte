# GitHub -> Hostinger VPS

## Regra principal

O Git guarda **código**. A VPS guarda **dados** no volume Docker. Não misture os dois.

## Subir este pacote para um repositório novo

No PowerShell, dentro da pasta do projeto:

```powershell
git init
git branch -M main
git add .
git commit -m "Central CT-e R12.13.9 - baseline limpa"
git remote add origin https://github.com/SEU_USUARIO/SEU_REPOSITORIO.git
git push -u origin main
```

Crie o repositório como **Private** no GitHub e não marque a opção de criar README remoto, pois este pacote já possui um.

## Clonar na Hostinger

```bash
ssh root@IP_DA_VPS
apt update
apt install -y git
mkdir -p /opt/central-cte
git clone https://github.com/SEU_USUARIO/SEU_REPOSITORIO.git /opt/central-cte
cd /opt/central-cte/deploy/vps
cp .env.example .env
nano .env
```

Para repositório privado, use autenticação GitHub segura (token/SSH key). Não coloque token dentro de scripts ou do repositório.

Depois:

```bash
bash scripts/install_docker_ubuntu.sh
bash scripts/preflight.sh
bash scripts/deploy.sh
```

## Atualizar depois

```bash
cd /opt/central-cte
git pull
cd deploy/vps
bash scripts/update.sh
```

## Nunca commitar

- `deploy/vps/.env`
- backups de `/data`
- banco de usuários/sessões
- arquivos `.sswweb` reais
- PDFs/XMLs/faturas
- credenciais PostgreSQL, AWS/S3 ou tokens
