#!/usr/bin/env bash
# Run a Playwright probe against the running stack without ever letting npm
# write into the repository.
#
# WHY THIS EXISTS
# `npm install` writes node_modules into the CURRENT WORKING DIRECTORY. An ad-hoc
# probe that set the container's cwd to the repo root therefore created
# <repo>/node_modules — root-owned, untracked, and invisible to the frontend's
# own gitignore rule (which only covers apps/frontend/node_modules/).
#
# THE GATE
# The repo is bind-mounted READ-ONLY. A read-only bind mount is enforced by the
# kernel, not by file permissions, so it holds even for root inside the container.
# `npm install` cannot create anything under /work; it fails with EROFS instead of
# silently dirtying the tree. node_modules lives in a named docker volume mounted
# over the one path that legitimately needs writes, and output/ is mounted writable
# for screenshots.
#
# The only writable paths inside the container are:
#   /work/apps/frontend/node_modules   (named volume, reused across runs)
#   /work/output                       (host output/, for screenshots)
#
# USAGE
#   scripts/e2e-probe.sh <probe.mjs> [args…]
# where <probe.mjs> is relative to apps/frontend/scripts/ — or an absolute path
# inside /work.
#
#   scripts/e2e-probe.sh probe-overflow.mjs
#   scripts/e2e-probe.sh probe-sidebar.mjs --verbose
#
# Do NOT hand-roll `docker run -v "$PWD:/work" … npm install …` any more. Use
# this script; it is the only invocation that keeps the repo clean by
# construction.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PLAYWRIGHT_IMAGE="mcr.microsoft.com/playwright:v1.49.1-noble"
PLAYWRIGHT_VERSION="1.49.1"
NM_VOLUME="al-e2e-nm-${PLAYWRIGHT_VERSION}"

err() { echo "[e2e-probe] $*" >&2; }

if ! docker info >/dev/null 2>&1; then
  err "Docker not running"
  exit 1
fi

PROBE="${1:-}"
if [[ -z "$PROBE" ]]; then
  err "usage: scripts/e2e-probe.sh <probe.mjs> [args…]"
  exit 2
fi
shift

# Resolve the probe the same way the old ad-hoc commands did: bare names live in
# scripts/, anything else is passed through.
if [[ "$PROBE" != /* ]]; then
  PROBE="scripts/${PROBE}"
fi

BASE_URL="${AGENT_E2E_BASE_URL:-http://127.0.0.1:8088}"

# The read-only claim is only worth anything if it is true. Prove it before running
# anything: if the container can create a file at the repo root, the gate is not
# in place and we refuse to continue rather than discover the mess afterwards.
verify_readonly() {
  if docker run --rm -v "$ROOT:/work:ro" "$PLAYWRIGHT_IMAGE" \
       bash -lc 'touch /work/.e2e-probe-ro-test' >/dev/null 2>&1; then
    # Writable — clean up whatever it made and fail loudly.
    rm -f "$ROOT/.e2e-probe-ro-test"
    return 0   # reachable means NOT read-only
  fi
  return 1
}

if verify_readonly; then
  err "FATAL: the repo is writable inside the container — refusing to run."
  err "The read-only mount is not in effect. Do not continue."
  exit 1
fi
err "read-only mount verified: container cannot write to the repo"

if ! curl -sf "${BASE_URL}/health" >/dev/null 2>&1; then
  err "stack not healthy at ${BASE_URL} — starting agent-layer"
  ( cd "$ROOT" && docker compose up -d agent-layer >/dev/null )
  for _ in $(seq 1 40); do
    curl -sf "${BASE_URL}/health" >/dev/null 2>&1 && break
    sleep 1
  done
fi

mkdir -p "$ROOT/output"

# Build the in-container command with proper quoting so probe args survive.
printf -v PROBE_Q '%q ' "$PROBE"
for a in "$@"; do
  printf -v A_Q '%q ' "$a"
  PROBE_Q+="${A_Q}"
done

exec docker run --rm \
  --network host \
  -v "$ROOT:/work:ro" \
  -v "${NM_VOLUME}:/work/apps/frontend/node_modules" \
  -v "$ROOT/output:/work/output" \
  -w /work/apps/frontend \
  --env-file "$ROOT/.env" \
  -e AGENT_E2E_BASE_URL="$BASE_URL" \
  "$PLAYWRIGHT_IMAGE" \
  bash -lc "npm install playwright@${PLAYWRIGHT_VERSION} --no-save --no-package-lock >/dev/null 2>&1 \
    && npx playwright install chromium >/dev/null 2>&1 \
    && node ${PROBE_Q}"
