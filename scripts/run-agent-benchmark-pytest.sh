#!/usr/bin/env bash
# Live agent LLM benchmarks via pytest (-m benchmark).
# Requires: running AgentLayer, enabled LLM endpoints in Admin → Interfaces (or AGENT_BENCH_LLM_* in .env).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ -f .env ]]; then set -a; # shellcheck disable=SC1091
  source .env; set +a; fi

export AGENT_BENCH_LIVE="${AGENT_BENCH_LIVE:-1}"
export PYTHONPATH="${PYTHONPATH:-}:$ROOT"

BASE="${AGENT_BENCH_BASE_URL:-${AGENT_E2E_BASE_URL:-http://127.0.0.1:${AGENT_HTTP_PORT:-8088}}}"
export AGENT_BENCH_BASE_URL="$BASE"
export AGENT_E2E_BASE_URL="$BASE"

echo "[bench] health check $BASE/health"
if ! curl -sf "$BASE/health" >/dev/null; then
  echo "[bench] server not reachable — start AgentLayer first" >&2
  exit 1
fi

# Default: smoke (S1–S3) + workspace W1.
MARK="${AGENT_BENCH_PYTEST_MARK:-benchmark}"
echo "[bench] pytest tests/benchmarks/agent/test_live_benchmark.py -m \"$MARK\""
exec python3 -m pytest tests/benchmarks/agent/test_live_benchmark.py -m "$MARK" -v --tb=short "$@"
