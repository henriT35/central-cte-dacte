FROM python:3.13-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    CENTRAL_CTE_DATA_ROOT=/data \
    CENTRAL_CTE_HOST=0.0.0.0 \
    CENTRAL_CTE_PORT=8765 \
    CENTRAL_CTE_STRICT_PORT=1 \
    CENTRAL_CTE_ALLOW_REMOTE=1

RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates \
      curl \
      fontconfig \
      fonts-dejavu-core \
      libcairo2 \
      libffi8 \
      libgdk-pixbuf-2.0-0 \
      libharfbuzz0b \
      libharfbuzz-subset0 \
      libjpeg62-turbo \
      libpango-1.0-0 \
      libpangoft2-1.0-0 \
      libwebp7 \
      poppler-utils \
      shared-mime-info \
      tini \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd --gid 10001 centralcte \
    && useradd --uid 10001 --gid 10001 --create-home --shell /usr/sbin/nologin centralcte

WORKDIR /app
COPY deploy/vps/requirements-prod.txt /tmp/requirements-prod.txt
RUN python -m pip install --no-cache-dir -r /tmp/requirements-prod.txt

COPY engine/ /app/engine/
COPY bases/ /app/bases/
COPY tabelas/ /app/tabelas/
COPY web_local/ /app/web_local/
COPY deploy/vps/ /app/deploy/vps/
COPY deploy/vps/seed/partner_tables/ /app/seed/partner_tables/

RUN mkdir -p /data /app/cache /backups /monitor \
    && for directory in logs sessoes relatorios faturas xmls saida_html modelos config; do \
         rm -rf "/app/${directory}" && ln -s "/data/runtime/${directory}" "/app/${directory}"; \
       done \
    && mkdir -p /app/engine/central_cte_modular/legacy_core /app/engine/legacy \
    && rm -rf /app/engine/central_cte_modular/legacy_core/cache \
              /app/engine/central_cte_modular/legacy_core/sessoes \
              /app/engine/central_cte_modular/legacy_core/logs \
              /app/engine/legacy/cache \
              /app/engine/legacy/sessoes \
              /app/engine/legacy/logs \
              /app/engine/legacy/xmls \
              /app/engine/legacy/relatorios \
    && ln -s /app/cache/legacy_core /app/engine/central_cte_modular/legacy_core/cache \
    && ln -s /data/runtime/legacy_core/sessoes /app/engine/central_cte_modular/legacy_core/sessoes \
    && ln -s /data/runtime/legacy_core/logs /app/engine/central_cte_modular/legacy_core/logs \
    && ln -s /app/cache/legacy /app/engine/legacy/cache \
    && ln -s /data/runtime/legacy/sessoes /app/engine/legacy/sessoes \
    && ln -s /data/runtime/legacy/logs /app/engine/legacy/logs \
    && ln -s /data/runtime/legacy/xmls /app/engine/legacy/xmls \
    && ln -s /data/runtime/legacy/relatorios /app/engine/legacy/relatorios \
    && chmod 755 /app/deploy/vps/scripts/*.sh \
    && chown -R centralcte:centralcte /app /data /backups /monitor

USER centralcte:centralcte
EXPOSE 8765
ENTRYPOINT ["/usr/bin/tini", "--", "/app/deploy/vps/scripts/container_entrypoint.sh"]
CMD ["python", "-u", "web_local/server.py", "--host", "0.0.0.0", "--port", "8765", "--no-browser", "--strict-port"]
