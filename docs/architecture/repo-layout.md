# Repository layout (server vs plug-in content)

This repo uses a single tree with two roles:

## Application code (server)

- **`apps/backend/`** — FastAPI service, domain logic, DB, integrations **code** (Python package `apps.backend.*`). This is what you ship, version, and deploy; it is not optional “content”.
- **`apps/frontend/`** — Vite/React SPA built to `apps/frontend/dist`, served at `/app`.

Set **`PYTHONPATH`** to the **repository root** (Docker: `/app`). Tool modules under **`plugins/tools/`** use explicit imports such as `from plugins.tools.capabilities…` / `from plugins.tools.integrations…` (package `plugins` lives next to `apps` at the repo root).

## Plug-and-play **content** (data & extensions)

These directories hold **bundles** you can add, fork, or omit without changing core APIs:

| Path | Role |
|------|------|
| **`plugins/tools/`** | Agent tool modules (`TOOLS` / `HANDLERS`) scanned by the registry (see `AGENT_TOOL_DIRS`; defaults include `plugins/tools` and `plugins/workflows`). |
| **`plugins/workflows/`** | Workflow-style Python modules scanned together with tools where applicable. |
| **`plugins/dashboard/`** | Dashboard domain folders (`dashboard.kind.json`, templates, examples). The server discovers kinds under this tree. |
| **`plugins/image_generation/`** | ComfyUI JSON graphs and presets (e.g. Studio workflow files referenced from `studio_catalog`). |
| **`plugins/interfaces/`** | Optional out-of-band integrations (e.g. Discord/Telegram bots) deployed beside the app, not the web UI. |

**Naming note:** `apps/backend/dashboard/` is **server code** for `/v1/dashboards`; `plugins/dashboard/` is **content** (kinds/bundles). Same word, different layer.

## Operations

- **Docker** copies `apps/` and `plugins/` into the image; the UI build is copied to `apps/frontend/dist`.
- **Compose** volume for user-created tools: `plugins/tools/agent_created` → `/data/tools` by default (see `compose.yaml`).
