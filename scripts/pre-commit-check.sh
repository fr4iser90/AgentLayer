#!/usr/bin/env bash
# Fast checks before git commit (~1–2 min). No running Agent Layer server required.
#
# Bypass once: SKIP_PRE_COMMIT=1 git commit -m "..."
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ "${SKIP_PRE_COMMIT:-}" == "1" ]]; then
  echo "[pre-commit] SKIP_PRE_COMMIT=1 — skipping checks"
  exit 0
fi

echo "[pre-commit] backend unit tests (unittest discover)…"
if ! PYTHONPATH="$ROOT" python3 -m unittest discover -s tests -p 'test_*.py' -q; then
  echo "[pre-commit] FAILED — backend tests (see output above)" >&2
  exit 1
fi

echo "[pre-commit] frontend i18n tests (npm test)…"
if command -v npm >/dev/null 2>&1; then
  if ! (cd "$ROOT/apps/frontend" && npm test); then
    echo "[pre-commit] FAILED — frontend i18n tests" >&2
    exit 1
  fi
else
  echo "[pre-commit] warning: npm not in PATH — skipping frontend tests" >&2
  echo "[pre-commit] hint: nix-shell -p nodejs_22  (or ensure npm is on PATH)" >&2
fi

echo "[pre-commit] all checks passed"
