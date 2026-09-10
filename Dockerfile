FROM node:22-bookworm-slim AS agent_ui_builder

WORKDIR /build/apps/frontend
COPY apps/frontend/package.json apps/frontend/package-lock.json* ./
RUN npm ci

COPY apps/frontend/ ./
RUN npm run build

FROM python:3.11-slim-bookworm

# Pin for reproducible Chromium deps + seed (coding workspaces share PLAYWRIGHT_BROWSERS_PATH).
# Keep in sync with common project Playwright majors (e.g. LOGA3 → chromium-1208 / Playwright 1.58).
ARG PLAYWRIGHT_VERSION=1.58.2

RUN apt-get update \
    && apt-get install -y --no-install-recommends tzdata git ffmpeg ca-certificates gosu \
    && rm -rf /var/lib/apt/lists/*

# Node/npm/npx for coding-agent workspace shells (same major as UI builder).
# Copy only Node bits — do not overwrite Python under /usr/local/bin.
COPY --from=agent_ui_builder /usr/local/bin/node /usr/local/bin/node
COPY --from=agent_ui_builder /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -sf ../lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
    && ln -sf ../lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx \
    && node --version \
    && npm --version

# Playwright: OS libs + Chromium seed (copied onto the compose volume on first boot).
ENV PLAYWRIGHT_BROWSERS_PATH=/opt/ms-playwright-seed
RUN apt-get update \
    && npx --yes "playwright@${PLAYWRIGHT_VERSION}" install-deps chromium \
    && mkdir -p /opt/ms-playwright-seed \
    && npx --yes "playwright@${PLAYWRIGHT_VERSION}" install chromium \
    && chmod -R a+rX /opt/ms-playwright-seed \
    && rm -rf /var/lib/apt/lists/* /root/.npm /tmp/*
ENV PLAYWRIGHT_BROWSERS_PATH=/data/ms-playwright

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

COPY apps ./apps
COPY plugins ./plugins
COPY docs ./docs
COPY content ./content
COPY benchmarks ./benchmarks
COPY tests/benchmarks ./tests/benchmarks
COPY tests/e2e ./tests/e2e
COPY tests/__init__.py ./tests/__init__.py
COPY --from=agent_ui_builder /build/apps/frontend/dist ./apps/frontend/dist

# copy entrypoint script for alembic stamp/upgrade
COPY scripts/alembic_entrypoint.sh /usr/local/bin/alembic_entrypoint.sh
RUN chmod +x /usr/local/bin/alembic_entrypoint.sh

ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

EXPOSE 8080

ENTRYPOINT ["/usr/local/bin/alembic_entrypoint.sh"]
CMD ["uvicorn", "apps.backend.api.main:app", "--host", "0.0.0.0", "--port", "8080", "--proxy-headers", "--forwarded-allow-ips", "*"]
