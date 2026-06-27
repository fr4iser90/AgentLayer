---
doc_id: architecture-overview
domain: agentlayer_docs
tags: [architecture, overview]
---

## What it is

AgentLayer is an OpenAI-compatible HTTP API + tool runtime around local models (Ollama), with:

- a **tool registry** that loads Python tools from disk
- a **planner/executor tool loop** (`src/domain/agent.py`)
- a **first-party UI** (`interfaces/agent-ui/`)
- **dashboards** (generic dashboards: layout + JSON data + sharing)

## Main components

For the backend DDD target architecture, bounded context map, and migration
workflow, see `docs/architecture/ddd-architecture-map.md`.
For the executable checklist and repository checks, see
`docs/architecture/ddd-checklist.md`.

### HTTP API server

- Entry: `src/api/main.py`
- Chat: `src/domain/agent.py::chat_completion`
- Dashboard endpoints: `src/dashboard/router.py`
- Tool execution endpoint: `src/api/tools_api.py` (router)

### Tool runtime

- Registry scanning: `src/domain/plugin_system/registry.py`
- Tool execution: `src/domain/tool_executor.py` and `src/domain/plugin_system/tools.py`
- Capabilities: `docs/adr/0002-tool-capabilities-convention.md`
- Capability gates: `docs/adr/0003-capability-governance.md`

### Storage (Postgres)

- Migrations: `src/infrastructure/db/migrations/`
- Schema snapshot: `src/infrastructure/db/migrations/sql/schema.sql`
- DB helpers: `src/infrastructure/db/db.py`

### UI (agent-ui)

- Dashboard page: `interfaces/agent-ui/src/pages/DashboardPage.tsx`
- Dashboard blocks: `interfaces/agent-ui/src/features/dashboard/DashboardBlocks.tsx`

## Data flows (high level)

### Chat with tools

1. Client calls `POST /v1/chat/completions` (OpenAI-compatible).
2. `src/domain/agent.py` merges tool specs from the registry.
3. The model may return tool calls.
4. AgentLayer runs tool calls deterministically via the Executor.
5. Tool results are appended as messages; loop continues for a few rounds.

See ADR 0001: `docs/adr/0001-tool-and-agent-architecture.md`.

### Dashboards

1. UI calls `GET /v1/dashboards` to list and load the catalog metadata.
2. UI calls `POST /v1/dashboards` to create a dashboard from an installed template kind.
3. UI persists layout+data to the backend via dashboard update endpoints.

Dashboards are generic (kind + layout + data). Specific “apps” (pets/shopping) are templates + optional tools.

