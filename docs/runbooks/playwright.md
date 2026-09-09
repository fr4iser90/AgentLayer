---
doc_id: runbook-playwright
domain: agentlayer_docs
tags: [runbook, playwright, coding-agent, docker]
---

## What this covers

How **Playwright / Chromium** is shared across coding workspaces in the AgentLayer server container (LOGA3 fetch, e2e, etc.).

## Default layout (docker compose)

| Piece | Value |
|-------|--------|
| Env | `PLAYWRIGHT_BROWSERS_PATH=/data/ms-playwright` |
| Volume | `agent_ms_playwright` → `/data/ms-playwright` |
| Image seed | `/opt/ms-playwright-seed` (Chromium + OS deps from Dockerfile `PLAYWRIGHT_VERSION`) |
| First boot | `alembic_entrypoint.sh` copies seed → volume if no `chrome` binary exists yet |

All project workspaces under `AGENTLAYER_WORKSPACE_PATH` inherit the same browser cache via coding `bash` (env scrub keeps `PLAYWRIGHT_*`).

## After image rebuild

```bash
docker compose build agent-layer
docker compose up -d agent-layer
```

First start seeds the volume (log: `seeding Playwright browsers`). Later app rebuilds reuse the volume unless you delete it.

## Project uses a different Playwright major

From the workspace root (coding bash):

```bash
npx playwright install chromium
```

Browsers are versioned under `PLAYWRIGHT_BROWSERS_PATH` (`chromium-<revision>/…`), so multiple Playwright versions can coexist.

## Missing browser / OS libs

| Symptom | Fix |
|---------|-----|
| `Executable doesn't exist at …/chrome` | `npx playwright install chromium` in the workspace, or recreate volume + restart so seed copies again |
| Shared libs missing | Rebuild image (Dockerfile runs `playwright install-deps chromium`) |
| Empty / wrong path | Ensure compose sets `PLAYWRIGHT_BROWSERS_PATH` and mounts `agent_ms_playwright` |

Reset cache (forces re-seed on next start):

```bash
docker compose stop agent-layer
docker volume rm agentlayer_agent_ms_playwright   # name may include project prefix — check `docker volume ls`
docker compose up -d agent-layer
```

## Container resources (compose)

Defaults target **one coding agent** that may run **Playwright** plus **1–3 small apps/scripts** inside `agent-layer` (same process namespace as `bash`):

| Service | Default limit | Notes |
|---------|---------------|--------|
| `agent-layer` | **6G** RAM · **3** CPUs · **`shm_size` 512mb** | Chromium + Node apps share this budget; raise `AGENT_SHM_SIZE=1gb` if Chromium crashes on `/dev/shm` |
| `postgres` | 1G · 1 CPU | App DB |
| `qdrant` | 768M · 1 CPU | Vectors |
| `neo4j` | 2G · 1.5 CPU | Heap/pagecache capped via `NEO4J_HEAP_*` / `NEO4J_PAGECACHE` |

Override in `.env` (see `.env.example`). Stack peak ≈ **~10G** — leave headroom on the host.

## Notes

- Headless Chromium in the **server** container is for automation in bound workspaces — not a substitute for the LOGA3 desktop GUI on the user’s machine when interactive login/2FA is required.
- E2E scripts under `scripts/run-e2e-playwright-*.sh` use the official Playwright Docker image separately; they do not depend on this volume.
