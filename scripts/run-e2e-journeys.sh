#!/usr/bin/env bash
# Run HTTP E2E journeys against a running Agent Layer (default http://127.0.0.1:8088).
# Requires a live LLM in GET /v1/models (LLM_PROVIDER_* or Admin LLM endpoints). No mock mode.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# Prevent concurrent runs. Two journeys against one instance interleave live LLM
# rounds and DB writes and surface ~25 httpx.ReadTimeout ghost failures that read
# like a security regression. Hold an exclusive lock for the whole run.
LOCK_FILE="${TMPDIR:-/tmp}/agentlayer-e2e-journeys.lock"
exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  echo "[e2e] another run-e2e-journeys.sh holds ${LOCK_FILE} — refusing to start a concurrent run" >&2
  exit 1
fi

if [[ -f .env ]]; then set -a; # shellcheck disable=SC1091
  source .env; set +a; fi
if [[ -f .env.e2e ]]; then set -a; # shellcheck disable=SC1091
  source .env.e2e; set +a; fi

BASE="${AGENT_E2E_BASE_URL:-http://127.0.0.1:${AGENT_HTTP_PORT:-8088}}"
echo "[e2e] health check $BASE/health"
if ! curl -sf "$BASE/health" >/dev/null; then
  echo "[e2e] server not reachable at $BASE — start compose / uvicorn first" >&2
  exit 1
fi

if [[ "${AGENT_E2E_SEED_USERS:-1}" != "0" ]]; then
  echo "[e2e] seed User B (if configured)"
  PYTHONPATH="$ROOT" python3 scripts/e2e/seed_users.py || true
fi

if [[ "${AGENT_E2E_CLEANUP_IDOR:-1}" != "0" ]]; then
  echo "[e2e] remove stale IDOR/E2E sandboxes (conversations, dashboards, workspaces)"
  PYTHONPATH="$ROOT" python3 scripts/e2e_cleanup.py || true
fi

MARK_EXPR="${AGENT_E2E_MARKERS:-e2e}"

echo "[e2e] pytest tests/e2e -m \"$MARK_EXPR\""
exec python3 -m pytest tests/e2e -m "$MARK_EXPR" -v --tb=short
