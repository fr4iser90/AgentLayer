---
doc_id: feature-operator-agent
domain: agentlayer_docs
tags: [operator, admin, tools, agent, security]
---

## What it is

The **Operator** agent (`agent_id: "operator"`) is an **admin-only** chat assistant for this deployment: interfaces, tool catalog, scheduler jobs, and RAG search over ingested docs. It is **not** the Coding agent and does not use a project workspace by default.

- **Definition:** `plugins/agents/operator.py`
- **Access control:** `AGENT_MIN_ROLE = "admin"`. Non-admins cannot select this agent: `chat_completion` rejects agents whose `min_role` is `admin` when the DB role is not `admin` (`apps/backend/domain/agent.py`).
- **System prompt:** directs the model to prefer reading state, respect tool policy, avoid inventing repo edits under `/code`, and to point at Admin UI or `PATCH /v1/admin/operator-settings` where appropriate.

## Operator vs personal (user) settings

**Do not fold “I’m Jürgen” into the Operator agent.** Operator is **admin-only** and targets **tenant/deployment** configuration. Personal preferences belong to the **signed-in user** and already have HTTP APIs (no admin role):

- `GET` / `PUT` `/v1/user/persona` — free-form persona text, optional inject into agent (`apps/backend/infrastructure/user_data_api.py`).
- `GET` / `PUT` `/v1/user/profile` — structured profile (`display_name`, locale, tone, …) via `AgentProfilePatch` in the same module.

**Product split:**

| Concern | Who | Typical tools / surface |
|--------|-----|-------------------------|
| Bridges, LLM endpoints, RAG admin, tenants, tool policies | **Operator** (admin) | Planned `operator_settings_*`, `interfaces_*`, setup links |
| Name, persona, language, personal prefs | **General** (or a future `personal` agent with `min_role: user`) | New thin tools: e.g. `user_profile_get`, `user_profile_patch`, `user_persona_get`, `user_persona_put` wrapping the same DB/HTTP logic |

That keeps RBAC obvious: a normal user must not need admin to set their display name.

## Recommended build order

1. **Operator Tier A tools** (read-only summaries, masked secrets) — high leverage for “what’s configured?” without waiting on a UI redesign.
2. **Operator Tier B/C** (validated patches + setup-session links for real secrets) — can ship incrementally per bridge.
3. **Admin UI polish** — in **parallel** or after Tier A; stable routes (`/admin/...`) matter more than pixels for deep links and agent copy.
4. **Personal tools on `general`** (or a dedicated low-privilege agent) — separate PR/track from operator; reuse `user_data_api` contracts.

## Admin configuration surface (code audit)

Everything below is implemented for **admin-authenticated** HTTP (`require_admin`), except routes decorated with `@require_permission` (admins still pass — see `apps/backend/infrastructure/auth.py`). Use this section as the **master checklist** for future Operator tools.

**Router wiring:** in the stock `apps/backend/api/main.py`, the **entire scheduler stack** is often commented out (`scheduler_jobs_router`, `scheduler_jobs_admin_router`, `scheduler_job_presets_router`, `scheduler_jobs_user_router`, and presets user router). `project_runs_router` is typically **enabled**. Re-enable routers when you need those HTTP paths live.

### HTTP: `apps/backend/api/main.py`

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/v1/admin/operator-settings` | Public/masked operator row (`operator_settings_public()`). |
| `PUT` | `/v1/admin/operator-settings` | **Narrow** replace: `OperatorSettingsPayload` — mainly `discord_application_id`, `integration_notes`. |
| `PATCH` | `/v1/admin/operator-settings` | Partial update via `OperatorSettingsPatch` (field groups below). |
| `GET` | `/v1/admin/external-llm/endpoints` | List external OpenAI-compatible endpoints (keys redacted; `api_key_last4`). |
| `PUT` | `/v1/admin/external-llm/endpoints` | Replace/sync all endpoint rows (`external_llm_endpoints_sync`). |
| `POST` | `/v1/admin/external-llm/models` | Probe `GET …/v1/models` using body or stored credentials. |
| `GET` | `/v1/admin/interfaces` | `interface_hints_public()` — application ids + `agent_mode` + effective mode. |
| `PUT` | `/v1/admin/interfaces` | `InterfaceHintsPayload` — Discord/Telegram application ids + `agent_mode` (clears `optional_connection_key`). |
| `GET` | `/v1/admin/tenants` | List tenants. |
| `POST` | `/v1/admin/tenants` | Create tenant. |
| `GET` | `/v1/admin/users` | List users. |
| `POST` | `/v1/admin/users` | Create password user (`email`, `password`, `role`, `tenant_id`). |
| `PATCH` | `/v1/admin/users/{user_id}` | Patch `tenant_id`, `workspace_quota`, `workspace_self_allowed`. |

### HTTP: tool registry (`apps/backend/api/tools_api.py`)

| Method | Path | Purpose | Notes |
|--------|------|---------|--------|
| `GET` | `/v1/admin/tools` | Tool metadata + operator policy rows. | `require_admin` |
| `POST` | `/v1/admin/reload-tools` | Rescan plugin tool directories. | `require_admin` |
| `PUT` | `/v1/admin/tool-policies` | Replace entire operator tool policy table. | `require_admin` |
| `POST` | `/v1/admin/create-tool` | Server-side `create` codegen. | `require_admin` |

### HTTP: RAG admin (`apps/backend/api/rag_api.py`, mounted as `rag_router`)

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/v1/admin/rag/ingest` | Ingest text into pgvector RAG for admin’s tenant; body: `text`, optional `domain`, `title`, `source_uri`. |
| `POST` | `/v1/admin/rag/ingest-docs` | Walk `docs_root` for `*.md`; optional `purge_first`, `domain`. |

### HTTP: persisted scheduler jobs — admin API (`scheduler_jobs_admin_api.py`)

Prefix when mounted: `/v1/admin/scheduler-jobs`

| Method | Path pattern | Purpose |
|--------|----------------|---------|
| `GET` | `/` | List jobs (filters: `dashboard_id`, `include_global`, `include_archived`, `execution_target`, `enabled`, `limit`). |
| `POST` | `/` | Create job. |
| `PATCH` | `/{job_id}` | Update fields. |
| `PATCH` | `/{job_id}/archived` | Archive / unarchive. |
| `DELETE` | `/{job_id}` | Hard delete. |
| `PATCH` | `/{job_id}/enabled` | Enable/disable. |

**Overlap:** Chat tools `schedule_job_*` use the same store but **not** all admin-only actions (e.g. hard delete).

### HTTP: scheduler presets (`scheduler_job_presets_api.py`)

When mounted: `GET /v1/admin/scheduler-job-presets` — templates from `plugins/schedules/presets/*.json`.

### HTTP: IDE job queue (`scheduler_jobs_api.py`)

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/v1/scheduler/jobs/due` | Due `ide_agent` jobs for current user (admin-only handler). |
| `POST` | `/v1/scheduler/jobs/{job_id}/ack-run` | Ack after IDE execution. |

### HTTP: project runs (`project_runs_api.py`)

Prefix: `/v1/project-runs` (admin-only handlers; not under `/v1/admin/…`).

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/v1/project-runs` | Enqueue one-shot IDE run. |
| `GET` | `/v1/project-runs` | List runs. |

### `PATCH /v1/admin/operator-settings` — field groups (`OperatorSettingsPatch`)

Source: `apps/backend/infrastructure/operator_settings.py`. `public_dict()` already hides raw bot tokens (`*_token_configured` flags).

| Group | PATCH fields (representative) |
|-------|-------------------------------|
| **Discord** | `discord_application_id`, `integration_notes`, `discord_bot_enabled`, `discord_bot_token`, `discord_trigger_prefix`, `discord_chat_model` |
| **Telegram** | `telegram_bot_enabled`, `telegram_bot_token`, `telegram_trigger_prefix`, `telegram_chat_model` |
| **Dashboard uploads** | `dashboard_upload_max_file_mb`, `dashboard_upload_allowed_mime` |
| **LLM** | `operator_external_llm_endpoints` (catalog providers), optional `llm_smart_routing_enabled`, `llm_router_*`, `llm_route_*` heuristics |
| **Memory** | `memory_graph_*`, `memory_enabled` |
| **RAG** | `rag_*`, `docs_root` |
| **PIDEA** | `pidea_*` |
| **Diagnostics** | `expose_internal_errors`, `http_client_log_level` |
| **Legacy server scheduler** | `scheduler_enabled`, `scheduler_interval_minutes`, `scheduler_model`, `scheduler_*` caps and tool modes, `scheduler_instructions`, … |
| **Scheduler jobs worker** | `scheduler_jobs_worker_enabled`, `scheduler_jobs_ide_pidea_*` |
| **Workspaces** | `workspace_allow_self_editing` |

**DB columns not on `OperatorSettingsPatch` today:** `discord_bot_agent_bearer`, `telegram_bot_agent_bearer`, `optional_connection_key` — still in the row / SQL writer; extending PATCH or a **dedicated secret form** may be required before an Operator tool can manage them safely.

### Suggested Operator tool bundles (HTTP → tools)

| Admin area | Read (Tier A) | Write / action (Tier B/C) |
|------------|---------------|---------------------------|
| Operator row | `operator_settings_summary` (wrap `GET` + merge `public_dict`) | `settings_patch` (validated `PATCH`); tokens via **setup link** where possible |
| Interfaces | same summary or `interfaces_get` | `interfaces_put` |
| External LLM | `external_llm_endpoints_list` | `external_llm_endpoints_put`, `external_llm_models_probe` |
| Tenants / users | `tenants_list`, `users_list` | `tenant_create`, `user_create`, `user_patch` |
| Tool registry | `tools_catalog` (shape of `GET /v1/admin/tools`) | `tool_policies_put`, `reload_tools`, `admin_create_tool` (high risk — confirm UX) |
| RAG | `rag_search` (exists) + optional `admin_rag_config_snapshot` | `rag_ingest`, `rag_ingest_docs` |
| Persisted `scheduler_jobs` | extend listing (archived/filters) vs current `list` | `scheduler_job_patch`, `scheduler_job_delete`, `admin_scheduler_job_archive` |
| Presets | `scheduler_presets_list` | — (read-only) |
| IDE queue | `admin_ide_jobs_due`, `admin_ide_job_ack` | thin wrappers |
| Project runs | `project_runs_list` | `run_create` |

Names are **indicative**; align with `TOOL_ID` / plugin layout when implementing.

## Tools today (allowlist)

The operator’s tool surface is resolved from `plugins/agents/operator.py` (`AGENT_TOOL_CAPABILITY_ANY`, …) and `apps/backend/domain/agent_registry.py` (`get_agent`); admin handlers live in `plugins/tools/capabilities/platform/operator_admin.py`:

| Tool | Role |
|------|------|
| `list` | List tool names (meta discovery). |
| `list_available_tools` | Broader listing helper. |
| `list_tool_categories` | Categories for the catalog. |
| `list_tools_in_category` | Tools in one category. |
| `get_tool_help` | JSON Schema / help for a tool name. |
| `read` | Read tool source (when policy allows). |
| `rag_search` | Search ingested RAG corpus (respects operator RAG settings). |
| `list` | List persisted scheduler jobs for the tenant. |
| `create` | Create a job (`execution_target` = registry `agent_id`; workspace agents need `workspace_id`). |
| `set_enabled` | Enable/disable a job. |

Implementation pointers:

- Scheduler tools: `plugins/tools/capabilities/platform/scheduler_jobs/scheduler_jobs.py`
- RAG tool: `plugins/tools/capabilities/knowledge/rag/rag.py` (uses `operator_settings` for enable/top_k, etc.)
- **Operator admin console:** `plugins/tools/capabilities/platform/operator_admin.py` — `TOOL_MIN_ROLE = "admin"`, capability `operator.console`. Allowlist patterns: `operator_settings_*`, `operator_interfaces_*`, `operator_external_llm_*`, `admin_*`.

### Operator admin console (implemented)

| Tool | Purpose |
|------|---------|
| `settings_get` | Masked settings + interface hints |
| `settings_patch` | `OperatorSettingsPatch` fields only |
| `interfaces_get` / `interfaces_put` | Application IDs + `agent_mode` |
| `external_llm_endpoints_get` / `…_put` | External LLM endpoint rows |
| `external_llm_models_list` | Probe `GET …/v1/models` (sync HTTP) |
| `tenants_list` / `tenant_create` | Tenants |
| `users_list` / `user_create` / `user_patch` | Users |
| `tools_catalog` / `tool_policies_put` / `reload_tools` | Tool registry + policies |
| `rag_ingest` / `rag_ingest_docs` | RAG ingest |
| `admin_scheduler_job_*` | List/create/patch/enable/archive/delete persisted jobs |
| `scheduler_presets_list` | Preset JSON templates |
| `project_runs_list` / `run_create` | IDE project runs |

## What the operator cannot do yet (Web-UI parity)

Until the **Suggested Operator tool bundles** in [Admin configuration surface](#admin-configuration-surface-code-audit) exist as real `tools[]` entries, the Operator can only **describe** behaviour — not apply it. Chat tools already cover a **subset** of scheduler actions when the plugin tools are allowed; they do not replace admin HTTP for tenants, policies, RAG ingest, etc.

## Planned / recommended tools (roadmap)

Goal: **chat-first configuration** with **secrets outside the LLM** where possible. Prefer small, auditable tools over one mega-patch.

### Tier A — Read-only and safe status (highest priority)

| Planned tool | Purpose |
|--------------|---------|
| `operator_settings_summary` | Return **non-secret** snapshot: flags, URLs, “configured yes/no”, masked tokens (e.g. last 4 chars), integration health hints. Backed by `operator_settings` public/masked dict. |
| `interfaces_summary` | Read-only view of `/v1/admin/interfaces`-equivalent data the admin is allowed to see (no raw secrets). |
| `bridge_status` | Per-bridge (Discord, Telegram, …): enabled, webhook/missing fields, last error from logs **if** safe to expose. |

### Tier B — Structured writes (no raw secrets in tool args)

| Planned tool | Purpose |
|--------------|---------|
| `settings_patch` | Strictly validated subset of `OperatorSettingsPatch` keys; **reject** unknown paths; rate-limit; audit log. **Do not** accept full bot tokens if avoidable. |
| `interfaces_put` | Thin wrapper over admin interfaces PUT with validation (or split per subsystem). |

### Tier C — Secrets and onboarding (safest UX)

| Planned tool | Purpose |
|--------------|---------|
| `admin_setup_link_create` | Create short-lived `setup_id` + URL to a **browser form** where the user pastes tokens; chat only receives a link + expiry. |
| `admin_setup_status` | Poll `{ "discord": "pending"|"configured" }` without returning secret material. |

Optional later: per-integration narrow tools (`discord_bridge_set_enabled`, `telegram_bot_set_webhook`, …) so the model cannot over-scope JSON patches.

## Security notes (secrets and LLM)

- **Avoid** passing API keys, bot tokens, or long-lived credentials through **user messages, assistant text, or tool arguments** when possible: chat retention, logs, and prompt-injection risk all grow with that pattern.
- **Prefer** Admin UI forms or **setup-session URLs** that POST secrets **directly** to the backend over TLS; the agent sees only **status** and **links**.
- **Optional later:** chat-side **ingress pipeline** (extract → encrypted vault → placeholders for the LLM → tools resolve handles server-side) — proposed spec: [`docs/adr/0006-chat-secret-ingress-pipeline.md`](../adr/0006-chat-secret-ingress-pipeline.md).
- Tools that write secrets should **never echo** the plaintext back in tool results; logs should **redact** sensitive fields.

## Related files

- Agent plugin: `plugins/agents/operator.py`
- Registry allowlist: `plugins/agents/operator.py` + `apps/backend/domain/agent_registry.py` (`AGENT_TOOL_CAPABILITY_ANY` / domain resolution)
- Admin gate: `apps/backend/infrastructure/auth.py` (`require_admin`)
- Operator settings service: `apps/backend/infrastructure/operator_settings.py`
- Settings HTTP API: `apps/backend/api/main.py` (`/v1/admin/operator-settings`)

## Changelog (doc maintenance)

- **Initial:** Documented current operator tools and planned tiers for Web-UI parity and secret-safe flows.
- **Scope:** Clarified operator vs personal user settings (`/v1/user/profile`, `/v1/user/persona`) and recommended build order (tools vs UI vs personal).
- **Admin audit:** Full `require_admin` HTTP inventory + `OperatorSettingsPatch` field groups + suggested Operator tool bundle mapping.
- **Shipped:** `operator_admin` plugin module (`plugins/tools/capabilities/platform/operator_admin.py`) with 26 tools; operator agent allowlist via capabilities (`plugins/agents/operator.py`).
- **Proposed:** Chat secret ingress — [`docs/adr/0006-chat-secret-ingress-pipeline.md`](../adr/0006-chat-secret-ingress-pipeline.md).
