#!/usr/bin/env bash
# Seed all-block demo dashboard + Playwright per-block screenshots.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if ! docker info >/dev/null 2>&1; then
  echo "[ux-audit] Docker not running" >&2
  exit 1
fi

BASE="${AGENT_E2E_BASE_URL:-http://127.0.0.1:8088}"
if ! curl -sf "$BASE/health" >/dev/null; then
  echo "[ux-audit] Starting agent-layer…"
  docker compose up -d agent-layer
  for _ in $(seq 1 60); do
    curl -sf "$BASE/health" >/dev/null && break
    sleep 1
  done
fi

echo "[ux-audit] Seeding dashboard…"
python3 "$ROOT/scripts/seed_dashboard_ux_audit.py"

echo "[ux-audit] Playwright screenshots…"
docker run --rm \
  --network host \
  -v "$ROOT:/work" \
  -w /work/apps/frontend \
  --env-file "$ROOT/.env" \
  -e AGENT_E2E_BASE_URL="$BASE" \
  mcr.microsoft.com/playwright:v1.49.1-noble \
  bash -lc 'npm install playwright@1.49.1 --no-save && npx playwright install chromium && node scripts/e2e-playwright-dashboard-ux-audit.mjs'

echo "[ux-audit] Done. See example/dashboard-ux-audit/"
