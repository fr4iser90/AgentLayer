#!/usr/bin/env bash
# Run Playwright i18n E2E in Docker (no local npm required).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if ! docker info >/dev/null 2>&1; then
  echo "[e2e] Docker not running" >&2
  exit 1
fi

if ! curl -sf "${AGENT_E2E_BASE_URL:-http://127.0.0.1:8088}/health" >/dev/null; then
  echo "[e2e] Starting agent-layer (docker compose up -d)…"
  docker compose up -d agent-layer
  for _ in $(seq 1 40); do
    curl -sf "${AGENT_E2E_BASE_URL:-http://127.0.0.1:8088}/health" >/dev/null && break
    sleep 1
  done
fi

docker run --rm \
  --network host \
  -v "$ROOT:/work" \
  -w /work/apps/frontend \
  --env-file "$ROOT/.env" \
  -e AGENT_E2E_BASE_URL="${AGENT_E2E_BASE_URL:-http://127.0.0.1:8088}" \
  mcr.microsoft.com/playwright:v1.49.1-noble \
  bash -lc 'npm install playwright@1.49.1 --no-save && npx playwright install chromium && node scripts/e2e-playwright-i18n.mjs'
