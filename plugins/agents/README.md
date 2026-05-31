# Agent plugins (`plugins/agents/`)

Each agent is one directory:

- **`agent.yaml`** — metadata, tool policy (`tool_domains`, `tool_capability_any`), behaviour flags
- **`system_prompt.md`** — system prompt (or set `system_prompt_file` in yaml)

**Tool allowlists** — union of:

- **`tool_domains`** — tools whose module `TOOL_DOMAIN` matches (plus `shared`)
- **`tool_capability_any`** — tools declaring any listed capability

`apps/backend/domain/agent_registry.py` resolves names against the **live** tool registry.

Admin overview: **Admin → Agents** (`GET /v1/admin/agents`).

See [`docs/features/agent-registry-and-allowlists.md`](../../docs/features/agent-registry-and-allowlists.md).
