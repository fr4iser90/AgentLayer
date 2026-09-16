---
doc_id: agent-registry-allowlists
domain: agentlayer_docs
tags: [agents, tools, registry, orchestration]
---

## Purpose

When you add **tools** or **agents**, you want **one** place that describes what a tool “is” (`TOOL_DOMAIN`, capabilities), and **agent plugins** that select tools **from that metadata**—not a second, hand-maintained list of every function name.

Today that split is implemented in:

- Tool metadata: each tool module under `plugins/tools/` (loaded by `apps/backend/domain/plugin_system/registry.py`).
- Agent allowlists: each `plugins/agents/<agent_id>/agent.yaml`, loaded by `apps/backend/domain/agent_runtime/plugin_loader.py` and resolved in `apps/backend/domain/agent_runtime/registry.py` (`get_agent`, `resolve_agent_tool_names`).

> **Field-name note.** Older drafts of this page used the Python-module spellings
> (`AGENT_TOOL_DOMAINS`, `AGENT_MIN_ROLE`, `AGENT_STRICT_WORKSPACE`, …). Those were the
> legacy `.py` agent plugins and are **not** the current YAML keys. Agents are YAML now:
> the loader reads lowercase snake_case keys (`tool_domains`, `min_role`,
> `strict_workspace`, …) and emits the registry dict. Use the YAML names below.


## Adding a new tool (author checklist)

Set on the **tool module** (same file as `HANDLERS` / `TOOLS`):

| Field | Required? | Role |
|--------|-----------|------|
| `TOOL_DOMAIN` | **Strongly yes** | Lowercase string, e.g. `coding`, `rag`, `operator`. The registry stores it on `tools_meta`; agents can allow **whole domains** via `tool_domains`. Use `shared` only for truly cross-cutting tools. |
| `TOOL_CAPABILITIES` | Recommended | Package-wide capability strings (see `docs/adr/0002-tool-capabilities-convention.md`). The registry builds `capability_index`; agents can allow via `tool_capability_any`. |
| `AGENT_TOOL_META_BY_NAME` | Optional | Per-function overrides (`capabilities`, `min_role`, …). |

**Practical rule:** pick a `TOOL_DOMAIN` that matches the **agent persona** that should see the tool by default (e.g. all workspace file tools → `coding`). If one package exports both “coding” and “explain” style tools, split modules or use per-tool meta so an agent can target **capabilities** instead of a broad domain.

## Adding a new agent (`plugins/agents/<agent_id>/`)

Create a directory with **`agent.yaml`** (metadata + tool policy) and **`system_prompt.md`** (prompt text). `id` defaults to the directory name; `system_prompt` may be inlined in the YAML or read from `system_prompt_file` (default `system_prompt.md`).

Tool-selection keys in **`agent.yaml`**:

1. **`tool_allowlist`** — an explicit list of tool names. **This short-circuits everything else:** if `tool_allowlist` is non-empty, `resolve_agent_tool_names` returns exactly that list (intersected with the live registry) and `tool_domains` / `tool_capability_any` are **ignored**. Use it when the surface is a fixed, curated set — `coding` and `coding_plan` do this.
2. **`tool_domains`** — union of all tools whose package `domain` is listed. Best when a whole vertical shares one domain. `shared` is **not** included unless you also set `tool_include_shared: true`.
3. **`tool_capability_any`** — union of tools whose **effective** capability matches **any** listed string. Best for admin/operator surfaces (e.g. `operator.console`, `scheduler.job.read`) or read-only slices of a broad domain (e.g. `coding.read` without `coding.execute`).
4. **`tool_include_introspection`** — if you select by domain/capability and still need `list_available_tools` / `get_tool_help`.

Without `tool_allowlist`, resolution is the **union** of (2)+(3), filtered against the **live** tool registry. Disabled or removed tool plugins simply disappear from `tool_names`.

Other keys the loader reads: `name`, `icon`, `description`, `min_role` (`user` default), `tool_domain` (single primary domain, metadata only — not the selection list), `requires_workspace`, `strict_workspace`, `schedulable` (default `true`), `execution_context` (`auto` default), `model_profile`, `coding_tools_permission_ask`, `tool_discipline_preset`, `pinned_tools`, `tool_forward_prefer_full_schema`, `delegatable`, `admin_only_delegatable`, `external_runtime`.

## Optional chat-loop behaviour (no hard-coded agent ids)

These **optional** `agent.yaml` keys (defaults false / unset) are resolved once per turn by
`_agent_behavior_flags()` — `domain/agent_runtime/agent_behavior.py` and
`application/agent_runtime/runtime/prompts.py` — and enforced downstream. No planner code keys
off an `agent_id` for these:

| YAML key | Default | Where it bites |
|--------|---------|----------------|
| `strict_workspace` | `false` | Chat fails when no **resolved** project workspace is available (checked in `application/agent_runtime/runtime/io.py`). |
| `coding_tools_permission_ask` | `false` | Threaded into `tool_context` by `chat_run_bootstrap.py`; enforced in `application/agent_runtime/use_cases/chat_tool_execution.py` against the `_CODING_TOOLS_PERMISSION_ASK` frozenset (`runtime/tool_loop.py`) when the client also sets `agent_permission_ask`. May require a WebSocket `permission_reply` before the tool runs. |
| `tool_discipline_preset` | unset | `turn_hooks_for_agent()` in `domain/agent_runtime/turn_hooks.py`. Only `dashboard` maps to real hooks (`DashboardTurnHooks` in `domain/agent_runtime/dashboard_guards.py`); `coding_build`, `coding_plan` and `security_auditor` are accepted values that currently resolve to no-op hooks — they are prompt/persona vocabulary, not enforcement. |
| `external_runtime` | unset | If set to a registered runtime id (e.g. `qwen_code`), the turn runs in that **external process** instead of AgentLayer's planner loop. The tool policy below is still resolved and stored, but the vendor's own tools do the work — the allowlist no longer bounds what runs. Refusing to run degrades to AgentLayer's loop only with `AGENT_EXTERNAL_RUNTIME_FALLBACK_INTERNAL=true`. See `docs/features/external-agent-runtimes.md` and `docs/adr/0010-external-agent-runtime-port.md`. |

The planner loop itself is `application/agent_runtime/use_cases/chat_completion.py` →
`chat_tool_loop.py`. There is no `apps/backend/domain/agent.py` — older drafts of this page
pointed there.

**Legacy `.py` agent modules.** `registry.py` still accepts a Python-module agent definition
(`source_kind: "python"`) that reads the old `AGENT_*` constants (`AGENT_MIN_ROLE`,
`AGENT_STRICT_WORKSPACE`, `AGENT_TOOL_DISCIPLINE_PRESET`, …) into the same registry dict. No
shipped agent uses it — every agent under `plugins/agents/` is a YAML directory. Treat the
module path as a compatibility fallback, not a template.

## Why this helps a future orchestrator

An orchestrator (top-level “router” agent) does not need a duplicate manifest of every tool name if tools already declare **`TOOL_DOMAIN`** and **`TOOL_CAPABILITIES`**. It can:

- Route a user intent to a **worker agent_id** + optional **capability hints** (already supported in chat via `agent_capability_hints` in the planner path), and/or
- Choose a downstream agent whose **`tool_domains` / `tool_capability_any`** align with the same metadata.

So: **declare domain + capabilities on the tool once**; agents and future orchestration **subscribe** to slices of that space.

## Current built-in examples

Most shipped agents pick an explicit **`tool_allowlist`**; only `operator` selects by capability.

- **`coding`** — `tool_allowlist` (53 tools: `apply_patch`, `bash`, `edit`, `git_push`, `create_pull_request`, …), `tool_domain: coding`, `requires_workspace: true`, `delegatable: true`. Full build surface.
- **`coding_plan`** — `tool_allowlist` (27 tools) narrowed to read/meta: no `write`, `bash` or `apply_patch`. Adds `strict_workspace: true`. Same entitlement as `coding` so existing roles keep working.
- **`security_auditor`** — `tool_allowlist` (37 tools), `strict_workspace: true`, `min_role: admin`.
- **`operator`** — `tool_capability_any: [operator.console, knowledge.retrieve, scheduler.job.read, scheduler.job.write, meta.discover, meta.inspect]`, `min_role: admin`, `schedulable: false`, `admin_only_delegatable: true`. The only capability-selected agent; admin handlers declare `TOOL_DOMAIN = "operator"` and `operator.console` per function.
- **`general`** / **`knowledge_companion`** — small explicit `tool_allowlist`s. These two are also the end-user default set — see the access layer below.

## Who may invoke which agent (access layers)

Tool selection decides **what an agent can do**. A separate layer decides **who may pick that
agent at all**. Both are needed: a resolved allowlist is worthless if the wrong user can start
the agent.

Enforced at exactly one place — `user_may_invoke_agent()` in
`apps/backend/domain/agent_runtime/access.py`, which delegates the policy arithmetic to
`resolve_agent_access()` in `domain/agent_runtime/governance.py`. Callers: the chat turn
(`application/agent_runtime/use_cases/chat_run_bootstrap.py`) and the bridge path
(`infrastructure/integrations/bridge_agent_session.py`). The chat picker is filtered by the
same function (`application/agent_runtime/use_cases/agent_catalog.py`), so what a user sees
is what they can send.

Four layers, evaluated in this order:

1. **`min_role: admin`** (agent.yaml) — a **hard** denial for non-elevated callers. No access
   policy can lift it (`direct_hard_denied` in `governance.py`). Today: `operator`, `reviewer`,
   `security_auditor`.
2. **End-user default set** — a non-elevated caller may directly invoke only `general` and
   `knowledge_companion` (`_ENDUSER_DIRECT_AGENT_IDS`).
3. **Tenant allowlist `chat.allowed_agent_ids`** (runtime config, set by tenant templates) —
   enforced **only for non-elevated callers**; unset means no tenant-level restriction.
4. **`agent_access_policies` rows** — `scope ∈ {global, tenant, user}` with
   `direct_state` / `delegate_state ∈ {inherit, allow, deny}`. Rows are read
   `global → tenant → user` and the **last non-`inherit` wins**, so a user row overrides a
   tenant row, which overrides a global row. This is the layer the People-admin UI writes.

**Elevation source.** "Elevated" means `users.site_role = 'site_admin'`, resolved through
`db.user_site_admin()` — **not** the legacy `users.role` column. See
[`docs/adr/0011-roles-and-agent-access-without-tenancy.md`](../adr/0011-roles-and-agent-access-without-tenancy.md)
for why, and for the delegated-admin capability model (`users.capabilities`).

**Known gap (not closed).** Scheduled jobs do **not** consult layers 3 and 4.
`domain/scheduling/targets.py` checks only `schedulable` and `min_role`, so a user with the
schedules entitlement can reach an agent through a job that is blocked for them in chat.
Treat that as an open hardening item, not as an accepted design.

## See also

- `docs/adr/0001-tool-and-agent-architecture.md` — layers, capability index.
- `docs/adr/0002-tool-capabilities-convention.md` — naming capabilities.
- `docs/adr/0006-chat-secret-ingress-pipeline.md` — optional chat → vault → placeholders for operator apply (proposed).
- `apps/backend/domain/plugin_system/tool_routing.py` — `filter_merged_tools_by_domain`, router categories.
- `docs/features/operator-agent.md` — operator persona and admin tools.
- `docs/features/external-agent-runtimes.md` — agents whose turn runs outside the planner loop (`external_runtime`).
- `docs/adr/0011-roles-and-agent-access-without-tenancy.md` — the roles / tenancy / delegated-admin decision behind the access layers above.
