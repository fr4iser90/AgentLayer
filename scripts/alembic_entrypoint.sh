#!/bin/sh
set -e
# Match Dockerfile WORKDIR (/app): Alembic config lives under apps/backend/...
if [ -f /app/apps/backend/infrastructure/db/alembic.ini ]; then
  cd /app
else
  echo "alembic_entrypoint: no alembic.ini under /app/apps/backend/infrastructure/db" >&2
  exit 1
fi

# When started as root (default compose): drop to the host user who owns the repo bind-mount
# so ./workspace and tools are not written as root. Plain `docker compose up -d` — no wrapper.
# Override: HOST_UID/HOST_GID or PUID/PGID. Never hardcode 1000.
resolve_host_ids() {
  if [ -n "${HOST_UID:-}" ] && [ -n "${HOST_GID:-}" ]; then
    return 0
  fi
  if [ -n "${PUID:-}" ] && [ -n "${PGID:-}" ]; then
    HOST_UID=$PUID
    HOST_GID=$PGID
    return 0
  fi
  for probe in /workspace/AgentLayer /code; do
    if [ -e "$probe" ]; then
      HOST_UID=$(stat -c '%u' "$probe")
      HOST_GID=$(stat -c '%g' "$probe")
      return 0
    fi
  done
  HOST_UID=0
  HOST_GID=0
}

fix_data_owner() {
  _uid=$1
  _gid=$2
  for d in /data/project_workspaces /data/tools "$BROWSERS_PATH"; do
    [ -d "$d" ] || continue
    cur=$(stat -c '%u' "$d")
    if [ "$cur" = "0" ] && [ "$_uid" != "0" ]; then
      chown -R "$_uid:$_gid" "$d" || true
    fi
  done
}

# Shared Playwright browser cache (all coding workspaces).
# Merge image seed into the volume so image upgrades add new chromium-<rev> trees
# without wiping revisions already installed by projects (cp -n / no-clobber).
BROWSERS_PATH="${PLAYWRIGHT_BROWSERS_PATH:-/data/ms-playwright}"
SEED_PATH="${PLAYWRIGHT_BROWSERS_SEED:-/opt/ms-playwright-seed}"

if [ "$(id -u)" -eq 0 ]; then
  resolve_host_ids
  mkdir -p "$BROWSERS_PATH"
  if [ -d "$SEED_PATH" ] && find "$SEED_PATH" -type f -name chrome -print -quit 2>/dev/null | grep -q .; then
    echo "alembic_entrypoint: merging Playwright browser seed into $BROWSERS_PATH" >&2
    if ! cp -an "$SEED_PATH"/. "$BROWSERS_PATH"/ 2>/dev/null; then
      for d in "$SEED_PATH"/*; do
        [ -e "$d" ] || continue
        base=$(basename "$d")
        if [ ! -e "$BROWSERS_PATH/$base" ]; then
          cp -a "$d" "$BROWSERS_PATH/$base"
        fi
      done
    fi
  elif ! find "$BROWSERS_PATH" -type f -name chrome -print -quit 2>/dev/null | grep -q .; then
    echo "alembic_entrypoint: no Playwright Chromium seed; run: npx playwright install chromium" >&2
  fi
  if [ "$HOST_UID" != "0" ]; then
    fix_data_owner "$HOST_UID" "$HOST_GID"
    echo "alembic_entrypoint: dropping privileges to uid=${HOST_UID} gid=${HOST_GID}" >&2
    exec gosu "$HOST_UID:$HOST_GID" "$0" "$@"
  fi
else
  mkdir -p "$BROWSERS_PATH" 2>/dev/null || true
  if [ -d "$SEED_PATH" ] && find "$SEED_PATH" -type f -name chrome -print -quit 2>/dev/null | grep -q .; then
    if ! find "$BROWSERS_PATH" -type f -name chrome -print -quit 2>/dev/null | grep -q .; then
      echo "alembic_entrypoint: merging Playwright browser seed into $BROWSERS_PATH" >&2
      cp -an "$SEED_PATH"/. "$BROWSERS_PATH"/ 2>/dev/null || true
    fi
  fi
fi

alembic -c apps/backend/infrastructure/db/alembic.ini upgrade head
exec "$@"
