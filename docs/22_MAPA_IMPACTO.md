# 22 — Mapa de Impacto
- `central_cte_engine_1_1_36.py`: XML, DACTE, relatórios, faturas, regras. Exige regressão comercial.
- Catálogo XLSX: identificação, percentuais, mínimos, extras/regiões e status.
- `server.py`: API, upload, jobs, bootstrap, autorização de rota.
- `security.py`: login, sessão, CSRF, usuários e auditoria.
- `official_dacte_service.py`: prévia/lote/decisão manual exibida.
- `official_signature_service.py`: perfil/recorte/PDF assinado visualmente.
- `compose.yaml`: serviços, volumes, hardening, healthcheck.
- `/data`: estado de produção; sempre backup antes de mudança destrutiva.
