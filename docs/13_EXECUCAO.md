# 13 — Execução
Local: `python web_local/server.py --host 127.0.0.1 --port 8765`.

Windows: `INICIAR_CENTRAL_CTE_WEB_LOCAL.bat` (local), `00_INICIAR_LOCAL_ONLINE.bat` (local+túnel), `00_PARAR_LOCAL_ONLINE.bat` (parada).

Docker: `python -u web_local/server.py --host 0.0.0.0 --port 8765 --no-browser --strict-port`.

Portas: 8765 aplicação; 80/443 Caddy; 5432 PostgreSQL quando aplicável.
