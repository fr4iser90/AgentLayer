#!/usr/bin/env bash
# One-shot local stack for this repo: Compose (API/DB) + Vite UI.
# Usage (repo root): ./start.sh
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

# Host port for agent-layer (compose maps ${AGENT_HTTP_PORT:-8088}:8080).
# Vite must proxy there — not container-internal 8080.
if [[ -z "${AGENT_HTTP_PORT:-}" && -f .env ]]; then
  AGENT_HTTP_PORT="$(grep -E '^[[:space:]]*AGENT_HTTP_PORT=' .env | tail -1 | cut -d= -f2- | tr -d '[:space:]"'"'" || true)"
fi
PORT="${AGENT_HTTP_PORT:-8088}"
export AGENT_API_TARGET="http://127.0.0.1:${PORT}"

docker network create ai-net 2>/dev/null || true
docker compose up -d

echo "Waiting for API at ${AGENT_API_TARGET} …"
ok=0
for _ in $(seq 1 60); do
  if curl -sf "${AGENT_API_TARGET}/auth/setup-status" >/dev/null 2>&1; then
    ok=1
    break
  fi
  sleep 1
done
if [[ "$ok" -ne 1 ]]; then
  echo "error: API not reachable at ${AGENT_API_TARGET}" >&2
  echo "  docker compose logs agent-layer | tail -50" >&2
  exit 1
fi

echo "API/UI (container): http://localhost:${PORT}/app/setup"
echo "Vite UI:            http://localhost:5173/app/setup  (proxy → ${AGENT_API_TARGET})"

# First-start: show setup token in this terminal (auto token lives in agent-layer logs).
STATUS_JSON="$(curl -sf "${AGENT_API_TARGET}/auth/setup-status" || true)"
if echo "${STATUS_JSON}" | grep -q '"needs_setup":true'; then
  SRC="$(echo "${STATUS_JSON}" | sed -n 's/.*"setup_token_source":"\([^"]*\)".*/\1/p' || true)"
  echo ""
  echo "======== Setup (first admin) ========"
  echo "Open: http://localhost:5173/app/setup"
  if [[ "${SRC}" == "env" ]]; then
    echo "Setup token: value of AGENT_SETUP_TOKEN in your .env (not printed here)"
  else
    # Banner may appear slightly after /auth/setup-status is up.
    # || true: awk exits early → compose logs gets SIGPIPE; pipefail must not kill start.sh.
    TOKEN=""
    for _ in $(seq 1 15); do
      TOKEN="$(
        docker compose logs agent-layer 2>/dev/null \
          | awk '/Einrichtungs-Token:/{getline; gsub(/\r/,""); sub(/^[^|]*\|[[:space:]]*/, ""); print; exit}' \
          || true
      )"
      TOKEN="${TOKEN#"${TOKEN%%[![:space:]]*}"}"
      TOKEN="${TOKEN%"${TOKEN##*[![:space:]]}"}"
      if [[ -n "${TOKEN}" ]]; then
        break
      fi
      sleep 1
    done
    if [[ -n "${TOKEN}" ]]; then
      echo "Setup token:"
      echo "${TOKEN}"
    else
      echo "Setup token: not found yet — run: docker compose logs agent-layer | tail -40"
    fi
  fi
  echo "===================================="
  echo ""
fi

cd "$ROOT/apps/frontend"
exec npm run dev
