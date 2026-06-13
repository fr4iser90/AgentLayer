# ADR 0001: Tool & Agent Architecture (scalability)

## Status

Accepted — 2026-04-08

## Context

The Agent Layer loads Python tools from disk, exposes them to chat (Ollama-compatible), applies operator policy, and runs a multi-round tool loop. Goals:

- **Capability before brand** (LLM reasons about `mail.read`, not `gmail_api_v3`).
- **Small atomic tools** (avoid monster handlers).
- **Machine-readable registry** for local LLMs and future planners.
- **Clear Planner vs Executor** boundaries.
- **Providers** swappable via user secrets (`service_key`), not tool IDs.
- **Workflows** remain a separate layer for multi-step jobs.
- **Room for memory** (retries, last good connection) without coupling to tool code.
- **Migrations** without breaking existing chat clients.

## Decision

### 1. Layers (conceptual)

| Layer | Responsibility |
|--------|----------------|
| **Registry** | Load `TOOLS`/`HANDLERS`, build `tools_meta`, capability index, router categories. |
| **Routing** | Narrow which tool *names* are sent to the LLM (triggers, `TOOL_DOMAIN`, **capability hints**). |
| **Planner** | The LLM + message loop in `chat_completion`: chooses tool calls from the slim catalog. |
| **Executor** | Deterministic dispatch: `execute_tool` → `run_tool` (policy, handler, logging). No LLM. |
| **Workflows** | Cron / separate registry; not inlined as mega-tools. |
| **Secrets** | `TOOL_SECRETS_REQUIRED` + `service_key`; `TOOL_REQUIRES` is *not* for secrets. |

### 2. Capabilities

- Declared in modules as **`TOOL_CAPABILITIES`** (package-wide) and optionally **`AGENT_TOOL_META_BY_NAME[name].capabilities`** (per function).
- Normalized strings, e.g. `mail.read`, `weather.get` (dot-separated **domain.action** recommended).
- Registry builds an inverted index: **`capability → [{ tool_name, package_id, domain }]`**.
- HTTP: **`GET /v1/capabilities`** exposes `schema_version` and the index for clients and future planners.
- Chat body: optional **`agent_capability_hints`**: list of capability strings; filters merged tools to those matching **any** hint (plus introspection tools), with a safe fallback if the filter would remove all non-introspection tools.

### 3. Planner / Executor (code)

- **`src/domain/agent.py`**: Planner (orchestrates Ollama + tool rounds). Imports **`execute_tool`** from **`src/domain/tool_executor.py`** for each tool call.
- **`src/domain/tool_executor.py`**: Single entry point for execution (wraps `run_tool`). Documented as the **Executor** surface for plugins and future step-runners.

### 4. Memory

- **`src/domain/tool_memory.py`**: Placeholder module documenting planned concerns (retry policy, last successful `service_key`, preferences). **Not** wired to DB yet — avoids fake persistence.

### 5. Folder layout (convention)

- `plugins/tools/capabilities/` — coding, filesystem, knowledge, browser, platform (operator, scheduler, secrets, tool_factory, …), creative.
- `plugins/tools/integrations/` — third-party HTTP APIs (GitHub, Gmail, weather, web search, …).
- `plugins/tools/productivity/` — calendar, todos, shopping list, RSS, ideas, pets, ….
- `plugins/tools/domains/` — vertical demos; not generic “provider” connectors.
- `plugins/tools/agent_created/` — optional mount for dynamically created tools (`AGENT_TOOLS_EXTRA_DIR`).

New connectors follow the same manifest fields; prefer **one generic IMAP** (presets) over N copy-paste modules when the protocol is identical.

**Layer boundary (enforced in CI):**

| Location | Allowed contents |
|----------|------------------|
| `plugins/tools/<domain>/` | Tool handlers (`HANDLERS`, `TOOLS`) **and** colocated libs (`lib/`, `common.py`, …) |
| `apps/backend/domain/` | Platform only: `plugin_system/`, agent runtime, `async_wait.py`, `identity.py`, … |
| `apps/backend/infrastructure/` | DB, HTTP APIs, workspace services — may **import** plugin libs, must not define tool domains |

Tool integration packages (`mail`, `github`, `security_scan`, `tool_factory`, `coding`/workspace) must **not** live under `apps/backend/domain/`. See `tests/unit/test_layer_boundaries.py`.

Colocated lib examples:

- `plugins/tools/integrations/mail/lib/`
- `plugins/tools/integrations/github/lib/`
- `plugins/tools/workspace/lib/` — bash policy, index, retrieval, LSP helpers
- `plugins/tools/security/security_scan/common.py`
- `plugins/tools/platform/tool_factory/common.py`
- `plugins/tools/integrations/http/lib/` — SSRF, HTTP profiles, connector execution
- `plugins/tools/integrations/friends/lib/` — friend lookup, calendar secrets
- `plugins/tools/integrations/messaging/lib/` — Telegram/Discord outbound
- `plugins/tools/workspace/lib/plan_search_policy.py` — Plan-agent tool guards

### 6. Migration

- **No DB migration** for ADR 0001.
- Existing tools without `TOOL_CAPABILITIES` appear in **`tools_unclassified`** on `/v1/capabilities` until authors add metadata.
- Chat defaults unchanged if `agent_capability_hints` is omitted.

## Consequences

- Local/small models can use **`GET /v1/capabilities`** + hints instead of scanning huge tool lists.
- Authors should add **`TOOL_CAPABILITIES`** incrementally; Admin/UI can surface unclassified tools.
- Full “capability-only” routing (no tool names in planner) is a **future** step; this ADR adds the index and HTTP contract first.

## Alternatives considered

- **Single mega-manifest file** outside Python: rejected as primary source; disk remains truth, HTTP exposes derived JSON.
- **Hard planner/executor processes**: deferred; clear modules + API suffice for v1.

## See also

- [0002-tool-capabilities-convention.md](./0002-tool-capabilities-convention.md) — `domain.action` vocabulary for `TOOL_CAPABILITIES`.
