#!/usr/bin/env bash
# Full-stack live validation orchestrator.
#
# Chains the pieces that already exist into one run with a report, because
# until now every one of them had to be invoked by hand and nothing said
# which of them passed.
#
# Design notes worth knowing before editing:
#
#  * Stages continue past failure and are summarised at the end. A live
#    validation wants the whole picture in one pass; stopping at the first
#    red means re-running everything to learn about the second one.
#  * Browser stages never overlap the journeys. The journeys drive live LLM
#    rounds and an 88-combination i18n pass; the app stops answering during
#    that, and a browser probe fired then times out and reads as a defect.
#  * Output goes to files, not through `| tail`. Piping block-buffers and
#    leaves you blind mid-run.
#  * The mode matrix sets the mode and verifies the read-back before any
#    browser probe. The frontend falls back to multi_tenant for an unknown
#    value, so a mode that failed to apply would otherwise be validated as
#    multi_tenant and every single_user assertion would pass against the
#    wrong instance.
#
# Usage:
#   scripts/validate_stack.sh                     # everything
#   scripts/validate_stack.sh --stage 4           # one stage
#   scripts/validate_stack.sh --from 3            # from a stage onward
#   scripts/validate_stack.sh --skip journeys     # skip by name
#   scripts/validate_stack.sh --model chat        # chat model_default for bootstrap
#
# Exit: 0 if all run stages passed, 1 otherwise.

set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO" || exit 2

# ---------------------------------------------------------------- args
FROM=0
ONLY=""
SKIP=""
MODEL="chat"
STAGES=(preflight up bootstrap seed backend journeys modematrix blocks report)

while [[ $# -gt 0 ]]; do
  case "$1" in
    --stage) ONLY="$2"; shift 2 ;;
    --from)  FROM="$2"; shift 2 ;;
    --skip)  SKIP="$SKIP,${2}"; shift 2 ;;
    --model) MODEL="$2"; shift 2 ;;
    -h|--help)
      sed -n '2,32p' "${BASH_SOURCE[0]}"
      exit 0 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

STAMP="$(date +%Y%m%d-%H%M%S)"
OUT="$REPO/output/stack-validation/$STAMP"
mkdir -p "$OUT/screenshots"

declare -A STATUS=()
declare -A DETAIL=()
RC_GLOBAL=0

idx_of() {
  local i=0
  for s in "${STAGES[@]}"; do
    [[ "$s" == "$1" ]] && { echo "$i"; return; }
    i=$((i+1))
  done
  echo "-1"
}

should_run() {
  local name="$1" i
  i="$(idx_of "$name")"
  [[ "$i" -lt "$FROM" ]] && return 1
  [[ -n "$ONLY" && "$ONLY" != "$name" ]] && return 1
  [[ ",$SKIP," == *",$name,"* ]] && return 1
  return 0
}

run_stage() {
  local name="$1" fn="$2"
  if ! should_run "$name"; then
    STATUS["$name"]="skip"; DETAIL["$name"]="not selected"
    return 0
  fi
  local log="$OUT/${name}.log"
  echo ""
  echo "══════════ ${name} ══════════"
  if "$fn" >"$log" 2>&1; then
    STATUS["$name"]="pass"; DETAIL["$name"]="see ${name}.log"
    echo "  PASS"
  else
    local rc=$?
    STATUS["$name"]="fail"; DETAIL["$name"]="exit ${rc}, see ${name}.log"
    RC_GLOBAL=1
    echo "  FAIL (exit ${rc}) — tail:"
    tail -n 15 "$log" | sed 's/^/    /'
  fi
}

# shellcheck disable=SC1091
load_env() { set -a; [ -f "$REPO/.env" ] && . "$REPO/.env"; [ -f "$REPO/.env.e2e" ] && . "$REPO/.env.e2e"; set +a; }

# ---------------------------------------------------------------- 0 preflight
stage_preflight() {
  local fail=0
  echo "config files"
  for f in .env .env.e2e; do
    if [[ -f "$REPO/$f" ]]; then echo "  ok: $f"; else echo "  MISSING: $f"; fail=1; fi
  done

  echo "required env keys"
  for k in AGENT_INITIAL_ADMIN_EMAIL AGENT_INITIAL_ADMIN_PASSWORD LLM_PROVIDER_1_BASE_URL AGENT_E2E_EMAIL_B AGENT_E2E_PASSWORD_B; do
    if [[ -n "${!k:-}" ]]; then echo "  ok: $k"; else echo "  MISSING: $k"; fail=1; fi
  done

  # Memory fall 2: files created at mode 600 break the image COPY and Alembic
  # crashes on the migration. Git tracks 100644, so fixing the mode makes no diff.
  echo "file modes"
  local bad
  bad="$(find apps plugins -type f -perm 600 ! -path '*__pycache__*' 2>/dev/null)"
  if [[ -n "$bad" ]]; then
    echo "  fixing mode 600 -> 644:"
    echo "$bad" | sed 's/^/    /'
    echo "$bad" | tr '\n' '\0' | xargs -0 -r chmod 644
  else
    echo "  ok: no mode-600 source files"
  fi

  echo "docker"
  docker info >/dev/null 2>&1 || { echo "  docker not reachable"; fail=1; }

  [[ $fail -eq 0 ]] || return 1
}

# ---------------------------------------------------------------- 1 up
stage_up() {
  echo "build"
  docker compose build agent-layer
  echo "up"
  docker compose up -d
  echo "waiting for /health"
  local port="${AGENT_HTTP_PORT:-8088}"
  for _ in $(seq 1 90); do
    if curl -sf "http://127.0.0.1:${port}/health" >/dev/null 2>&1; then
      echo "  healthy"
      return 0
    fi
    sleep 2
  done
  echo "  /health never came up"
  return 1
}

# ---------------------------------------------------------------- 2 bootstrap
stage_bootstrap() {
  python3 scripts/bootstrap_instance.py --model "$MODEL"
}

# ---------------------------------------------------------------- 3 seed
stage_seed() {
  echo "friend + sharing fixture"
  docker exec -i agent-layer-postgres psql -U agent -d agent \
    < scripts/seed_friend_sharing_fixture.sql

  # users.dashboard_quota defaults to 1 and every user already owns
  # "Personal dashboard", so a fresh instance rejects the very first
  # POST /v1/dashboards with 403 "Dashboard quota reached". That single
  # default took out the whole dashboard e2e set (9 IDOR-matrix tests,
  # the nested-ref test and the ux-audit seed), which all create
  # dashboards. Raising it is fixture setup, not a behaviour change.
  # Note the column is singular `dashboard_quota`, not `dashboards_quota`.
  echo "raise dashboard_quota for fixture users"
  docker exec -i agent-layer-postgres psql -U agent -d agent -c \
    "UPDATE users SET dashboard_quota = 25;"

  echo "dashboard ux-audit fixture"
  python3 scripts/seed_dashboard_ux_audit.py
}

# ---------------------------------------------------------------- 4 backend
stage_backend() {
  echo "friend/sharing deep matrix"
  docker compose run --rm -e PYTHONPATH=/code --entrypoint sh agent-layer \
    -c "cd /code && python /code/scripts/validate_friend_sharing_fixture.py"

  echo "tenancy preflight"
  docker compose run --rm -e PYTHONPATH=/code --entrypoint sh agent-layer \
    -c "cd /code && python /code/scripts/preflight_tenancy.py"

  echo "auth smoke (routes + api reachability)"
  python3 scripts/e2e_auth_smoke.py
}

# ---------------------------------------------------------------- 5 journeys
stage_journeys() {
  ./scripts/run-e2e-journeys.sh
}

# ---------------------------------------------------------------- 6 mode matrix
run_mode() {
  local mode="$1"
  echo "── mode: ${mode} ──"
  # Apply and verify the read-back before touching a browser.
  local tok
  tok="$(curl -s -X POST "http://127.0.0.1:${AGENT_HTTP_PORT:-8088}/auth/login" \
    -H 'Content-Type: application/json' \
    -d "{\"email\":\"${AGENT_INITIAL_ADMIN_EMAIL}\",\"password\":\"${AGENT_INITIAL_ADMIN_PASSWORD}\"}" \
    | python3 -c 'import sys,json;print(json.load(sys.stdin).get("access_token",""))')"
  [[ -n "$tok" ]] || { echo "  cannot log in to set mode"; return 1; }

  curl -s -X PATCH "http://127.0.0.1:${AGENT_HTTP_PORT:-8088}/v1/admin/operator-settings" \
    -H 'Content-Type: application/json' \
    -H "Authorization: Bearer ${tok}" \
    -d "{\"deployment_mode\":\"${mode}\"}" \
    | python3 -c "
import sys,json
d=json.load(sys.stdin)
got=str(d.get('deployment_mode','')).lower()
print('  read-back:', got)
sys.exit(0 if got=='${mode}' else 1)
" || { echo "  mode did not apply"; return 1; }

  docker run --rm --network host \
    -v "$REPO:/work" -w /work/apps/frontend \
    -e BASE_URL="http://127.0.0.1:${AGENT_HTTP_PORT:-8088}" \
    -e EMAIL="$AGENT_INITIAL_ADMIN_EMAIL" \
    -e PASSWORD="$AGENT_INITIAL_ADMIN_PASSWORD" \
    -e MODE="$mode" \
    -e OUT_DIR=/work/output/stack-validation/"$STAMP"/screenshots \
    mcr.microsoft.com/playwright:v1.49.1-noble \
    bash -lc 'npm install playwright@1.49.1 --no-save >/dev/null 2>&1 && node scripts/e2e-playwright-stack-surfaces.mjs'
}

stage_modematrix() {
  local fail=0
  for m in single_user agent_system multi_tenant; do
    run_mode "$m" || fail=1
  done
  # Leave the instance in the mode it started in.
  return $fail
}

# ---------------------------------------------------------------- 7 blocks
stage_blocks() {
  bash scripts/run-e2e-playwright-dashboard-ux-audit.sh
}

# ---------------------------------------------------------------- 8 report
stage_report() {
  local md="$OUT/report.md"
  {
    echo "# Stack validation — ${STAMP}"
    echo ""
    echo "| stage | status | detail |"
    echo "|---|---|---|"
    for s in "${STAGES[@]}"; do
      printf '| %s | %s | %s |\n' "$s" "${STATUS[$s]:-not-run}" "${DETAIL[$s]:-}"
    done
    echo ""
    echo "## Residue this run leaves behind"
    echo ""
    echo "scripts/e2e_cleanup.py only matches \`[E2E IDOR]\` / \`IDOR …\` / \`e2e-idor-ws-*\`."
    echo "It does **not** remove: the KC-pilot tenant and its 6 users, the"
    echo "\`e2e-agentlayer-git\` workspace, the seeded friendship and"
    echo "\`share_permissions\` rows, the ux-audit dashboards, or the seeded"
    echo "scheduler jobs. Wipe with \`docker compose down -v\` to clear all of it."
  } > "$md"

  cp "$OUT"/*.log "$OUT" 2>/dev/null || true
  echo "report: $md"
  echo ""
  echo "summary:"
  for s in "${STAGES[@]}"; do
    printf '  %-12s %s\n' "$s" "${STATUS[$s]:-not-run}"
  done
}

# ---------------------------------------------------------------- run
echo "AgentLayer full-stack validation — ${STAMP}"
echo "output: $OUT"

# Must run before any stage: the mode matrix and the browser probes read
# AGENT_INITIAL_ADMIN_* / AGENT_E2E_* straight from the environment, and
# defining load_env without calling it left those empty.
load_env

run_stage preflight   stage_preflight
run_stage up          stage_up
run_stage bootstrap   stage_bootstrap
run_stage seed        stage_seed
run_stage backend     stage_backend
run_stage journeys    stage_journeys
run_stage modematrix  stage_modematrix
run_stage blocks      stage_blocks
run_stage report      stage_report

exit $RC_GLOBAL
