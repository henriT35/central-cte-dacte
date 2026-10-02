# 12 — Instalação do Zero
## Windows
1. Clonar/extrair repositório limpo.
2. Ter Python compatível.
3. Executar `INICIAR_CENTRAL_CTE_WEB_LOCAL.bat` ou `00_INICIAR_LOCAL_ONLINE.bat`.
4. Abrir `http://127.0.0.1:8765`.
5. Criar o primeiro Desenvolvedor.
6. Importar Base SSW real.
7. Validar `/api/health` e um lote sentinela.

## VPS Ubuntu
```bash
apt update && apt install -y git
git clone https://github.com/henriT35/central-cte-dacte.git /opt/central-cte
cd /opt/central-cte/deploy/vps
bash scripts/install_docker_ubuntu.sh
```
IP temporário:
```bash
bash scripts/setup_ip_mode.sh IP_DA_VPS 8765
sudo bash scripts/configure_firewall.sh 22
bash scripts/preflight.sh
bash scripts/deploy.sh
```
Domínio: copiar `.env.domain.example` para `.env`, preencher valores e rodar firewall `domain`, preflight e deploy.
