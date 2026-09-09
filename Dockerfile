FROM node:22-bookworm-slim AS agent_ui_builder

WORKDIR /build/apps/frontend
COPY apps/frontend/package.json apps/frontend/package-lock.json* ./
RUN npm ci

COPY apps/frontend/ ./
RUN npm run build

FROM python:3.11-slim-bookworm

RUN apt-get update \
    && apt-get install -y --no-install-recommends tzdata git ffmpeg ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Node/npm/npx for coding-agent workspace shells (same major as UI builder).
# Copy only Node bits — do not overwrite Python under /usr/local/bin.
COPY --from=agent_ui_builder /usr/local/bin/node /usr/local/bin/node
COPY --from=agent_ui_builder /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -sf ../lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
    && ln -sf ../lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx \
    && node --version \
    && npm --version

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
