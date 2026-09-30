---
doc_id: feature-operator-agent
domain: agentlayer_docs
tags: [operator, admin, tools, agent, security]
---

## What it is

The **Operator** agent (`agent_id: "operator"`) is an **admin-only** chat assistant for this deployment: interfaces, tool catalog, scheduler jobs, and RAG search over ingested docs. It is **not** the Coding agent and does not use a project workspace by default.

- **Definition:** `plugins/agents/operator/agent.yaml` (`min_role: admin`, `delegatable: false`)
- **Access control:** `user_may_invoke_agent` (`apps/backend/domain/agent_runtime/access.py`) refuses any agent whose registry `min_role` is `admin` unless `is_elevated_role(user_role)` holds, so a normal account cannot select this agent in chat.
- **System prompt:** directs the model to prefer reading state, respect tool policy, avoid inventing repo edits under `/code`, and to point at Admin UI or `PATCH /v1/admin/operator-settings` where appropriate.

## Operator vs personal (user) settings

**Do not fold “I’m Jürgen” into the Operator agent.** Operator is **admin-only** and targets **tenant/deployment** configuration. Personal preferences belong to the **signed-in user** and already have HTTP APIs (no admin role):

- `GET` / `PUT` `/v1/user/persona` — free-form persona text, optional inject into agent (`apps/backend/api/platform/controllers/user_data_api.py`).
- `GET` / `PUT` `/v1/user/profile` — structured profile (`display_name`, locale, tone, …) via `AgentProfilePatch` in the same module.

**Product split:**

| Concern | Who | Typical tools / surface |
|--------|-----|-------------------------|
| Bridges, LLM endpoints, RAG admin, tenants, tool policies | **Operator** (admin) | `operator_admin` (`settings_*`, `interfaces_*`, `external_llm_*`, `tenants_*`, `users_*`, `tools_*`, `rag_*`, `scheduler_*`, `project_runs_*`); setup links for raw secrets still missing |
| Name, persona, language, personal prefs | **General** (or a future `personal` agent with `min_role: user`) | No tools yet — the HTTP routes above are the only surface; thin wrappers (`user_profile_get` / `_patch`, `user_persona_get` / `_put`) would reuse them |

That keeps RBAC obvious: a normal user must not need admin to set their display name.

## Recommended build order

1. ~~**Operator Tier A tools**~~ — done as the `operator_admin` console below; its remaining gap is the company-scope check, not coverage.
2. **Operator Tier C** (setup-session links for real secrets) — the only tier never built; until it exists, tokens stay in the Admin UI.
3. **Admin UI polish** — stable routes (`/admin/...`) matter more than pixels for deep links and agent copy.
4. **Personal tools on `general`** (or a dedicated low-privilege agent) — separate PR/track from operator; reuse `user_data_api` contracts.

## Admin configuration surface (code audit)

Three gates, and which one a route uses is the whole answer to *who* can reach it (helpers in `apps/backend/infrastructure/identity/auth.py`, re-exported for controllers by `apps/backend/application/identity/use_cases/request_auth.py`):

- `require_provider_admin` (`apps/backend/application/providers/use_cases/provider_admin_acl.py`) — **site admin, deliberately**: the operator row, the LLM catalog and the interface hints move every company at once and spend the instance's provider budget, so there is no capability slug for that surface.
- `require_site_admin` — tenants and their templates, the tool registry, RAG doc-ingest.
- `require_admin_scope(request, CAP_…)` → an `AdminScope` with role **and** the companies the caller was granted, so a delegated holder sees strictly less than a site admin on the same route. A row by id outside that range answers `404`, never `403` — a `403` would confirm which company owns it.

Use this section as the **master checklist** for future Operator tools.

**Router wiring:** `apps/backend/api/main.py` mounts the scheduler stack — `scheduler_jobs_admin_router`, `scheduler_jobs_user_router`, both run routers and the presets user router. Presets exist **once** (`/v1/user/scheduler-job-presets`, gated by the `users.schedules_allowed` feature flag); an older site-admin twin read the same directory and answered 403 for delegated `schedule.manage` holders.

### HTTP: operator settings, bridges, tenants (`apps/backend/api/providers/controllers/operator_settings_api.py`, `…/providers/controllers/external_llm_api.py`, `…/providers/controllers/interfaces_api.py`, `apps/backend/api/platform/controllers/admin_users_api.py`)

| Method | Path | Purpose | Gate |
|--------|------|---------|------|
| `GET` | `/v1/admin/operator-settings` | Public/masked operator row (`operator_settings_public()`). | provider admin |
| `PUT` | `/v1/admin/operator-settings` | **Narrow** replace: `OperatorSettingsPayload` — mainly `discord_application_id`, `integration_notes`. | provider admin |
| `PATCH` | `/v1/admin/operator-settings` | Partial update via `OperatorSettingsPatch` (field groups below). | provider admin |
| `GET` | `/v1/admin/external-llm/endpoints` | Chat endpoints (keys redacted; `api_key_last4`). Legacy path — storage is `operator_provider_endpoints`. | provider admin |
| `PUT` | `/v1/admin/external-llm/endpoints` | Replace/sync all chat endpoint rows. Legacy path. | provider admin |
| `GET` | `/v1/admin/external-llm/env-providers` | Preview `LLM_PROVIDER_N_*` env providers for an explicit import. Legacy path. | provider admin |
| `POST` | `/v1/admin/external-llm/env-providers/import` | Import the previewed env providers. Legacy path. | provider admin |
| `POST` | `/v1/admin/external-llm/models` | Probe `GET …/v1/models` using body or stored credentials. | provider admin |
| `GET` | `/v1/admin/provider-endpoints[/{kind}][/env-providers\|/models]`, `PUT /v1/admin/provider-endpoints/{kind}` | The generic surface those legacy routes forward to (`provider_endpoints_api.py`). | provider admin |
| `GET` | `/v1/admin/interfaces` | `interface_hints_public()` — application ids + `agent_mode` + effective mode. | provider admin |
| `PUT` | `/v1/admin/interfaces` | `InterfaceHintsPayload` — Discord/Telegram application ids + `agent_mode` (clears `optional_connection_key`). | provider admin |
| `GET` | `/v1/admin/tenant-templates` | Provisioning templates for a new tenant. | site admin |
| `GET` | `/v1/admin/tenants` | List tenants. | site admin |
| `POST` | `/v1/admin/tenants` | Create tenant (`name`, `template_id`, `seed_demo_content`). | site admin |
| `GET` | `/v1/admin/users` | List users **inside the caller's scope** — a delegated holder does not get every mailbox on the instance. | `user.manage` |
| `POST` | `/v1/admin/users` | Create password user (`email`, `password`, `role`, `tenant_id`). | `user.manage` |
| `PATCH` | `/v1/admin/users/{user_id}` | `tenant_id` (moving between companies is site-admin only), `workspace_quota`, `workspace_self_allowed`, `schedules_allowed`, `dashboards_allowed`, `dashboard_quota`, `media_*`, `llm_queue_priority`, `capabilities`. A delegated holder may never edit a site admin. | `user.manage` |

### HTTP: tool registry (`apps/backend/api/tools/controllers/tools_api.py`)

| Method | Path | Purpose | Notes |
|--------|------|---------|--------|
| `GET` | `/v1/admin/tools` | Tool metadata + operator policy rows. | `require_site_admin` |
| `POST` | `/v1/admin/reload-tools` | Rescan plugin tool directories. | `require_site_admin` |
| `PUT` | `/v1/admin/tool-policies` | Replace entire operator tool policy table. | `require_site_admin` |
| `POST` | `/v1/admin/create-tool` | Server-side `create` codegen. | `require_site_admin` |

### HTTP: RAG admin (`apps/backend/api/rag/controllers/rag_api.py`, mounted as `rag_router`)

The two routes are **not** gated the same way, and the difference is the reason this surface splits at all: text ingest is tenant data, a docs root is a server filesystem. Both answer `503` while RAG is disabled in operator settings.

| Method | Path | Gate | Purpose |
|--------|------|------|---------|
| `POST` | `/v1/admin/rag/ingest` | `require_admin_scope(request, CAP_KNOWLEDGE_MANAGE)` | Ingest text into pgvector RAG for a company; body `text`, optional `domain`, `title`, `source_uri`. |
| `POST` | `/v1/admin/rag/ingest-docs` | `require_site_admin` | Walk `docs_root` (caller-supplied path) for `*.md`; body `docs_root`, `domain` (default `agentlayer_docs`), `purge_first`, `incremental` (default true). |

### HTTP: persisted scheduler jobs — admin API (`scheduler_jobs_admin_api.py`)

Prefix when mounted: `/v1/admin/scheduler-jobs` — guarded by `require_admin_scope(request, CAP_SCHEDULE_MANAGE)`, so the reachable companies come from the caller's scope, not their own row.

| Method | Path pattern | Purpose |
|--------|----------------|---------|
| `GET` | `/` | List jobs (filters: `tenant_id`, `dashboard_id`, `include_global`, `include_archived`, `execution_target`, `enabled`, `limit`). |
| `POST` | `/` | Create job (`tenant_id` optional; a delegated holder may only name their own company). |
| `PATCH` | `/{job_id}` | Update fields. |
| `PATCH` | `/{job_id}/archived` | Archive / unarchive. |
| `DELETE` | `/{job_id}` | Hard delete. |
| `PATCH` | `/{job_id}/enabled` | Enable/disable. |

A site admin (`tenant_filter() is None`) sees every company; a delegated holder is pinned to their own and gets `403` when naming another. Rows outside a caller's scope answer `404` on the by-id routes — a `403` would confirm that another company has that job. Creates run the same two-layer target policy as the user API (registry `min_role` + the company's agent allowlist).

**Overlap:** the chat plugin's `create` / `list` / `set_enabled` tools and the operator console's `scheduler_job_*` tools hit the same store, but neither exposes every admin-only action (hard delete is console-only).

### HTTP: scheduler presets (`scheduler_job_presets_user_api.py`)

`GET /v1/user/scheduler-job-presets` — templates from `plugins/schedules/presets/*.json`, gated by `schedule_feature_permission_error` like the schedule list itself.

### HTTP: schedule runs (`scheduler_job_runs_api.py`)

A coding or workspace schedule is executed by the server-side worker (`scheduler_jobs_runner`), not by an editor that picks its work up: the due/ack queue an IDE extension used to poll (`GET /v1/scheduler/jobs/due`, `POST /v1/scheduler/jobs/{job_id}/ack-run` in `scheduler_jobs_api.py`) was retired with the `ide_agent` → `coding_agent` change, and both routes are gone rather than moved. What remains of that surface is the run history, `scheduler_job_runs` — read-only, and a job or run outside the caller's reach answers `404` on either side:

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/v1/user/scheduler-jobs/{job_id}/runs` | Runs of a job the caller may view. |
| `GET` | `/v1/user/scheduler-job-runs/{run_id}` | One run, after re-checking the run's job. |
| `GET` | `/v1/admin/scheduler-jobs/{job_id}/runs` | Runs of a job inside the caller's company scope (`schedule.manage`). |
| `GET` | `/v1/admin/scheduler-job-runs/{run_id}` | One run inside the caller's company scope. |

### HTTP: project runs (`apps/backend/api/projects/controllers/project_runs_api.py`)

Prefix: `/v1/project-runs` — not under `/v1/admin/…`, yet every handler calls `require_admin_scope(request, CAP_DASHBOARD_MANAGE)`, so runs are read and written inside the caller's granted companies only.

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/v1/project-runs` | Enqueue a one-shot coding run: `execution_target` is fixed to `coding` and `coding_workflow` must name a workspace. |
| `GET` | `/v1/project-runs` | List runs (filters: `dashboard_id`, `project_row_id`, `limit`). |
| `GET` | `/v1/project-runs/{run_id}` | One run of the caller's company. |

### `PATCH /v1/admin/operator-settings` — field groups (`OperatorSettingsPatch`)

Source: `apps/backend/infrastructure/settings/operator_settings.py`. `public_dict()` already hides raw bot tokens (`*_token_configured` flags).

| Group | PATCH fields (representative) |
|-------|-------------------------------|
| **Discord** | `discord_application_id`, `integration_notes`, `discord_bot_enabled`, `discord_bot_token`, `discord_trigger_prefix`, `discord_chat_model` |
| **Telegram** | `telegram_bot_enabled`, `telegram_bot_token`, `telegram_trigger_prefix`, `telegram_chat_model` |
| **Dashboard uploads** | `dashboard_upload_max_file_mb`, `dashboard_upload_allowed_mime` |
| **LLM** | `operator_external_llm_endpoints` (catalog providers), optional `llm_smart_routing_enabled`, `llm_router_*`, `llm_route_*` heuristics |
| **Memory** | `memory_graph_*`, `memory_enabled` |
| **RAG** | `rag_*`, `docs_root` |
| **Diagnostics** | `expose_internal_errors`, `http_client_log_level` |
| **Legacy server scheduler** | `scheduler_enabled`, `scheduler_interval_minutes`, `scheduler_model`, `scheduler_*` caps and tool modes, `scheduler_instructions`, … |
| **Scheduler jobs worker** | `scheduler_jobs_worker_enabled` |
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
| Persisted `scheduler_jobs` | `scheduler_job_list` (archived/filters beyond the chat tool's `list`) | `scheduler_job_patch`, `scheduler_job_delete`, `scheduler_job_set_archived` |
| Presets | `scheduler_presets_list` | — (read-only) |
| Project runs | `project_runs_list` | `run_create` |

Names are **indicative**; align with `TOOL_ID` / plugin layout when implementing.

## Tools today (allowlist)

The operator’s tool surface is a **capability grant**, not a tool list. `plugins/agents/operator/agent.yaml` declares `tool_capability_any`: `operator.console`, `knowledge.retrieve`, `scheduler.job.read`, `scheduler.job.write`, `meta.discover`, `meta.inspect` — resolved by `get_agent` (`apps/backend/domain/agent_runtime/registry.py`). A module attaches capabilities per declared tool name (`TOOL_CAPABILITIES`, `AGENT_TOOL_META_BY_NAME`), so one module can carry several capabilities at different `min_role`s:

| Capability | Unlocks | Source module |
|------------|---------|---------------|
| `operator.console` | the 26 admin actions in the table below (`min_role: admin`) | `plugins/tools/platform/operator/admin.py` |
| `knowledge.retrieve` | `rag_search` | `plugins/tools/knowledge/rag/rag.py` |
| `scheduler.job.read` | `list` — persisted jobs for the tenant | `plugins/tools/platform/scheduler/jobs.py` |
| `scheduler.job.write` | `create` (job; `execution_target` = registry `agent_id`, workspace agents need `workspace_id`), `set_enabled` | `plugins/tools/platform/scheduler/jobs.py` |
| `meta.discover` | `list` (tool names), `list_available_tools`, `list_tool_categories`, `list_tools_in_category` | `plugins/tools/platform/tool_factory/list.py`, `plugins/tools/platform/tool_help/help.py` |
| `meta.inspect` | `read` (tool source, when policy allows), `get_tool_help` | `plugins/tools/platform/tool_factory/read.py`, `plugins/tools/platform/tool_help/help.py` |

Names above are the **declared** `function.name`; the registry registers those verbatim and only qualifies with `TOOL_DOMAIN` when a name collides (`apps/backend/domain/plugin_system/registry.py`). `list`, `read` and `create` are declared by several modules, so a deployment can legitimately show `scheduler.list` or `tool_factory.read` — wire new surfaces to the **capability**, never to a bare name.

Implementation pointers:

- Scheduler tools: `plugins/tools/platform/scheduler/jobs.py` — `TOOL_ID = "scheduler_jobs"`, `TOOL_DOMAIN = "scheduler"`, declared names `create` / `list` / `set_enabled` (each at `min_role: user`)
- RAG tool: `plugins/tools/knowledge/rag/rag.py` (uses `operator_settings` for enable/top_k, etc.)
- **Operator admin console:** `plugins/tools/platform/operator/admin.py` — `TOOL_ID = "operator_admin"`, `TOOL_MIN_ROLE = "admin"`, capability `operator.console`. `plugins/agents/operator/agent.yaml` grants tools by **capability** (`tool_capability_any`), not by tool-name pattern.

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
| `scheduler_job_list` / `_create` / `_patch` / `_set_enabled` / `_set_archived` / `_delete` | Persisted jobs, admin store API |
| `scheduler_presets_list` | Preset JSON templates |
| `project_runs_list` / `run_create` | Coding project runs |

**The console is not gated like the HTTP routes above.** Every handler calls `_require_admin()`, which is `db.user_role(uid) == "admin"` — the legacy `users.role` column, not `site_role` + `capabilities`. Two consequences worth knowing before extending it: a delegated `user.manage` / `schedule.manage` holder gets **nothing** here (no capability slug is evaluated, so `tool_capability_any: operator.console` is the only door), and a plain `role: admin` account is **not** confined to its own company the way the routes confine one — `users_list` returns `list_all_users()` with no tenant filter, which is precisely what `GET /v1/admin/users` was changed to stop doing. Extending the console means routing handlers through the same `AdminScope`, not adding tools on top of the old check.

## What the operator cannot do yet (Web-UI parity)

The admin console above already implements most of the [suggested bundles](#suggested-operator-tool-bundles-http--tools) — reading and patching settings, interfaces, endpoints, tenants/users, tool policies, RAG ingest, jobs, presets, project runs. What is still open:

| Gap | Detail |
|-----|--------|
| Secrets out-of-band | `discord_bot_agent_bearer`, `telegram_bot_agent_bearer`, `optional_connection_key` are on neither `OperatorSettingsPatch` nor any tool — there is deliberately no chat path for them, but the setup-link flow that would replace it is unbuilt (`setup_link` / `setup_id` appear nowhere under `plugins/`). |
| Tool authoring | `POST /v1/admin/create-tool` has no tool counterpart; the console can list and re-policy the catalog, not generate code. |
| Tenant templates | `GET /v1/admin/tenant-templates` is HTTP-only, so `tenant_create` can be reached without ever seeing a valid `template_id`. |
| Other provider kinds | the console wraps the **legacy chat** endpoint routes; `/v1/admin/provider-endpoints/{kind}` (embedding and the rest) is HTTP-only. |
| Company scope | the console gate — see the caveat directly above. |

## Planned / recommended tools (roadmap)

Goal: **chat-first configuration** with **secrets outside the LLM** where possible. Prefer small, auditable tools over one mega-patch.

### Tier A — Read-only and safe status (highest priority)

| Planned tool | Purpose | Status |
|--------------|---------|--------|
| `operator_settings_summary` | Return **non-secret** snapshot: flags, URLs, “configured yes/no”, masked tokens (e.g. last 4 chars), integration health hints. | **Shipped** as `settings_get`. |
| `interfaces_summary` | Read-only view of `/v1/admin/interfaces`-equivalent data the admin is allowed to see (no raw secrets). | **Shipped** as `interfaces_get` (folded into `settings_get` too). |
| `bridge_status` | Per-bridge (Discord, Telegram, …): enabled, webhook/missing fields, last error from logs **if** safe to expose. | Open — the two above report configuration, not whether the bridge actually works. |

### Tier B — Structured writes (no raw secrets in tool args)

| Planned tool | Purpose | Status |
|--------------|---------|--------|
| `settings_patch` | Strictly validated subset of `OperatorSettingsPatch` keys; **reject** unknown paths. | **Shipped** — `OperatorSettingsPatch` fields only. Rate-limit and audit log were never added. |
| `interfaces_put` | Thin wrapper over admin interfaces PUT with validation (or split per subsystem). | **Shipped** as `interfaces_put`. |

### Tier C — Secrets and onboarding (safest UX)

| Planned tool | Purpose | Status |
|--------------|---------|--------|
| `admin_setup_link_create` | Create short-lived `setup_id` + URL to a **browser form** where the user pastes tokens; chat only receives a link + expiry. | Open. |
| `admin_setup_status` | Poll `{ "discord": "pending"|"configured" }` without returning secret material. | Open. |

Optional later: per-integration narrow tools (`discord_bridge_set_enabled`, `telegram_bot_set_webhook`, …) so the model cannot over-scope JSON patches.

## Security notes (secrets and LLM)

- **Avoid** passing API keys, bot tokens, or long-lived credentials through **user messages, assistant text, or tool arguments** when possible: chat retention, logs, and prompt-injection risk all grow with that pattern.
- **Prefer** Admin UI forms or **setup-session URLs** that POST secrets **directly** to the backend over TLS; the agent sees only **status** and **links**.
- **Optional later:** chat-side **ingress pipeline** (extract → encrypted vault → placeholders for the LLM → tools resolve handles server-side) — proposed spec: [`docs/adr/0006-chat-secret-ingress-pipeline.md`](../adr/0006-chat-secret-ingress-pipeline.md).
- Tools that write secrets should **never echo** the plaintext back in tool results; logs should **redact** sensitive fields.

## Related files

- Agent plugin: `plugins/agents/operator/agent.yaml`
- Registry allowlist: `plugins/agents/operator/agent.yaml` (`tool_capability_any`) resolved by `apps/backend/domain/agent_runtime/registry.py`
- Admin gate: `apps/backend/infrastructure/identity/auth.py` — `require_site_admin` for site-wide routes, `require_admin_scope(request, CAP_…)` wherever a delegated holder may act inside their granted companies (`require_admin_capability` answers only *what*, not *where*); controllers import these through `apps/backend/application/identity/use_cases/request_auth.py`
- Operator settings service: `apps/backend/infrastructure/settings/operator_settings.py`
- Settings HTTP API: `apps/backend/api/providers/controllers/operator_settings_api.py` (`/v1/admin/operator-settings`)

## Changelog (doc maintenance)

- **Initial:** Documented current operator tools and planned tiers for Web-UI parity and secret-safe flows.
- **Scope:** Clarified operator vs personal user settings (`/v1/user/profile`, `/v1/user/persona`) and recommended build order (tools vs UI vs personal).
- **Admin audit:** Full `require_admin` HTTP inventory + `OperatorSettingsPatch` field groups + suggested Operator tool bundle mapping.
- **Shipped:** `operator_admin` plugin module (`plugins/tools/capabilities/platform/operator_admin.py`) with 26 tools; operator agent allowlist via capabilities (`plugins/agents/operator.py`).
- **Proposed:** Chat secret ingress — [`docs/adr/0006-chat-secret-ingress-pipeline.md`](../adr/0006-chat-secret-ingress-pipeline.md).
- **Drift pass (2026-09-30):** Every path, route and guard re-derived from code. The IDE due/ack queue (`GET /v1/scheduler/jobs/due`, `POST /v1/scheduler/jobs/{job_id}/ack-run`) is gone — this page now documents what replaced it (`scheduler_job_runs` read routes); plugin paths are `plugins/agents/operator/agent.yaml`, `plugins/tools/platform/operator/admin.py`, `plugins/tools/platform/scheduler/jobs.py`; the guard names above are the ones the routers actually call. Entries before this one keep the paths as they read when written.
