#!/usr/bin/env bash
# Modular checks before git commit. No running Agent Layer server required.
#
# Bypass once: SKIP_PRE_COMMIT=1 git commit -m "..."
# Select profile: CHECK_PROFILE=fast git commit -m "..."
# Skip module: SKIP_CHECKS=node_cve,python_cve git commit -m "..."
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ "${SKIP_PRE_COMMIT:-}" == "1" ]]; then
  echo "[pre-commit] SKIP_PRE_COMMIT=1 — skipping checks"
  exit 0
fi

PROFILE="${CHECK_PROFILE:-precommit}"
echo "[pre-commit] running modular checks profile=$PROFILE"
if ! python3 "$ROOT/scripts/checks/run.py" --profile "$PROFILE"; then
  echo "[pre-commit] FAILED — fix checks above or use SKIP_CHECKS for intentional local-only skips" >&2
  exit 1
fi

echo "[pre-commit] all checks passed"
