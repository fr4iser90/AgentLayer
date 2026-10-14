#!/usr/bin/env bash
# Multi-viewport responsive overflow probe (Playwright in Docker).
# Needs a healthy agent-layer and AGENT_E2E_* credentials (.env / .env.e2e).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if ! docker info >/dev/null 2>&1; then
  echo "[responsive] Docker not running" >&2
  exit 1
fi

# shellcheck disable=SC1091
set -a
[ -f "$ROOT/.env" ] && . "$ROOT/.env"
[ -f "$ROOT/.env.e2e" ] && . "$ROOT/.env.e2e"
set +a

BASE="${AGENT_E2E_BASE_URL:-http://127.0.0.1:8088}"
# API health lives on the stack (8088), even when the UI base is Vite (:5173).
API_HEALTH="${AGENT_E2E_API_HEALTH_URL:-http://127.0.0.1:8088/health}"
if ! curl -sf "$API_HEALTH" >/dev/null; then
  echo "[responsive] Starting agent-layer…"
  docker compose up -d agent-layer
  for _ in $(seq 1 60); do
    curl -sf "$API_HEALTH" >/dev/null && break
    sleep 1
  done
fi
if ! curl -sf -o /dev/null --connect-timeout 2 "$BASE/" && ! curl -sf -o /dev/null --connect-timeout 2 "$BASE/app/login"; then
  echo "[responsive] UI base unreachable: $BASE" >&2
  echo "[responsive] Start Vite (npm run dev / ./start.sh) or set AGENT_E2E_BASE_URL=http://127.0.0.1:8088" >&2
  exit 1
fi

STAMP="$(date +%Y%m%d-%H%M%S)"
if [[ -n "${RESPONSIVE_OUT_DIR:-}" ]]; then
  OUT="$RESPONSIVE_OUT_DIR"
  # Host path under repo → /work/... for the container
  case "$OUT" in
    "$ROOT"/*) OUT_REL="${OUT#"$ROOT"/}" ;;
    /*) echo "[responsive] RESPONSIVE_OUT_DIR must be under $ROOT" >&2; exit 1 ;;
    *) OUT_REL="$OUT"; OUT="$ROOT/$OUT_REL" ;;
  esac
else
  OUT_REL="output/responsive/${STAMP}"
  OUT="$ROOT/$OUT_REL"
fi
mkdir -p "$OUT"

EXTRA_ARGS=("$@")
if [[ ${#EXTRA_ARGS[@]} -eq 0 ]]; then
  EXTRA_ARGS=(--shots fail)
fi

# Quote args for the inner bash -lc
INNER_ARGS=""
for a in "${EXTRA_ARGS[@]}"; do
  INNER_ARGS+=" $(printf '%q' "$a")"
done

echo "[responsive] Playwright probe → $OUT"
docker run --rm \
  --network host \
  -v "$ROOT:/work" \
  -w /work/apps/frontend \
  -e AGENT_E2E_BASE_URL="$BASE" \
  -e AGENT_E2E_EMAIL="${AGENT_E2E_EMAIL:-${AGENT_INITIAL_ADMIN_EMAIL:-}}" \
  -e AGENT_E2E_PASSWORD="${AGENT_E2E_PASSWORD:-${AGENT_INITIAL_ADMIN_PASSWORD:-}}" \
  -e AGENT_INITIAL_ADMIN_EMAIL="${AGENT_INITIAL_ADMIN_EMAIL:-}" \
  -e AGENT_INITIAL_ADMIN_PASSWORD="${AGENT_INITIAL_ADMIN_PASSWORD:-}" \
  -e RESPONSIVE_OUT_DIR="/work/${OUT_REL}" \
  mcr.microsoft.com/playwright:v1.49.1-noble \
  bash -lc "npm install playwright@1.49.1 --no-save >/dev/null 2>&1 && npx playwright install chromium >/dev/null 2>&1 && node scripts/e2e-responsive-probe.mjs${INNER_ARGS}"

echo "[responsive] Done. See $OUT (gitignored)"
