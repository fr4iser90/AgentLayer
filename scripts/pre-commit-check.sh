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

_run_frontend_i18n() {
  (cd "$ROOT/apps/frontend" && npm test)
}

_try_frontend_via_nix_shell() {
  if [[ ! -f "$ROOT/shell.nix" ]]; then
    return 127
  fi
  if ! command -v nix-shell >/dev/null 2>&1; then
    return 127
  fi
  echo "[pre-commit] running frontend i18n via nix-shell (shell.nix)…"
  nix-shell "$ROOT/shell.nix" --run "cd apps/frontend && npm test"
}

_run_frontend_with_nix_fallback() {
  if command -v npm >/dev/null 2>&1; then
    if _run_frontend_i18n; then
      return 0
    fi
    echo "[pre-commit] frontend i18n failed (npm in PATH)" >&2
    return 1
  fi

  echo "[pre-commit] npm not in PATH — trying nix-shell…" >&2
  local rc=0
  _try_frontend_via_nix_shell || rc=$?
  if [[ "$rc" -eq 0 ]]; then
    return 0
  fi
  if [[ "$rc" -eq 127 ]]; then
    echo "[pre-commit] ERROR: cannot run frontend i18n checks." >&2
    echo "[pre-commit]   Need npm on PATH or nix-shell + shell.nix in repo root." >&2
    echo "[pre-commit]   Fix: cd $ROOT && nix-shell   (then commit again)" >&2
    echo "[pre-commit] skipping frontend i18n (backend checks already ran)." >&2
    return 2
  fi
  echo "[pre-commit] frontend i18n failed inside nix-shell" >&2
  return 1
}

echo "[pre-commit] backend unit tests (unittest discover)…"
if ! PYTHONPATH="$ROOT" python3 -m unittest discover -s tests -p 'test_*.py' -q; then
  echo "[pre-commit] FAILED — backend tests (see output above)" >&2
  exit 1
fi

echo "[pre-commit] frontend i18n tests (npm test)…"
frontend_rc=0
_run_frontend_with_nix_fallback || frontend_rc=$?
case "$frontend_rc" in
  0) ;;
  1)
    echo "[pre-commit] FAILED — fix frontend/i18n before commit (same check as Docker npm run build)" >&2
    exit 1
    ;;
  2)
    # Environment could not run frontend checks — do not block commit.
    ;;
esac

echo "[pre-commit] all checks passed"
