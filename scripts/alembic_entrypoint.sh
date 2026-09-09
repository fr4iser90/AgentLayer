#!/bin/sh
set -e
# Match Dockerfile WORKDIR (/app): Alembic config lives under apps/backend/...
if [ -f /app/apps/backend/infrastructure/db/alembic.ini ]; then
  cd /app
else
  echo "alembic_entrypoint: no alembic.ini under /app/apps/backend/infrastructure/db" >&2
  exit 1
fi

# Shared Playwright browser cache (all coding workspaces). Volume may be empty on first boot.
BROWSERS_PATH="${PLAYWRIGHT_BROWSERS_PATH:-/data/ms-playwright}"
SEED_PATH="${PLAYWRIGHT_BROWSERS_SEED:-/opt/ms-playwright-seed}"
mkdir -p "$BROWSERS_PATH"
if ! find "$BROWSERS_PATH" -type f -name chrome -print -quit 2>/dev/null | grep -q .; then
  if [ -d "$SEED_PATH" ] && find "$SEED_PATH" -type f -name chrome -print -quit 2>/dev/null | grep -q .; then
    echo "alembic_entrypoint: seeding Playwright browsers into $BROWSERS_PATH" >&2
    cp -a "$SEED_PATH"/. "$BROWSERS_PATH"/
  else
    echo "alembic_entrypoint: no Playwright Chromium seed; run: npx playwright install chromium" >&2
  fi
fi

alembic -c apps/backend/infrastructure/db/alembic.ini upgrade head
exec "$@"
