#!/usr/bin/env bash
# Install (or refresh) .git/hooks/pre-commit → scripts/pre-commit-check.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOOK="$ROOT/.git/hooks/pre-commit"
CHECK="$ROOT/scripts/pre-commit-check.sh"

if [[ ! -d "$ROOT/.git" ]]; then
  echo "error: not a git repository ($ROOT)" >&2
  exit 1
fi

if [[ ! -x "$CHECK" ]]; then
  chmod +x "$CHECK"
fi

cat >"$HOOK" <<EOF
#!/usr/bin/env bash
# Installed by scripts/install-git-pre-commit-hook.sh — do not edit by hand.
set -euo pipefail
ROOT="\$(git rev-parse --show-toplevel)"
exec "\$ROOT/scripts/pre-commit-check.sh"
EOF

chmod +x "$HOOK"
echo "Installed pre-commit hook:"
echo "  $HOOK"
echo "Runs: $CHECK"
echo ""
echo "Bypass once: SKIP_PRE_COMMIT=1 git commit"
echo "Uninstall:   rm $HOOK"
