# Agent plugins (`plugins/agents/`)

Each `*.py` file defines one **agent persona** (`AGENT_ID`, prompts, optional `AGENT_TOOL_DOMAIN` for chat routing).

**Tool allowlists** are resolved from this file using `AGENT_TOOL_DOMAINS`, `AGENT_TOOL_CAPABILITY_ANY`, and/or `AGENT_TOOL_PATTERNS` (see `apps/backend/domain/agent_registry.py`).

**When adding tools elsewhere:** set `TOOL_DOMAIN` (and ideally `TOOL_CAPABILITIES`) on the tool module under `plugins/tools/` so agents do not need per-tool name lists.

Full convention (orchestrator-friendly): [`docs/features/agent-registry-and-allowlists.md`](../../docs/features/agent-registry-and-allowlists.md).
