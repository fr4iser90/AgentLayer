---
doc_id: agent-registry-allowlists
domain: agentlayer_docs
tags: [agents, tools, registry, orchestration]
---

## Purpose

When you add **tools** or **agents**, you want **one** place that describes what a tool “is” (`TOOL_DOMAIN`, capabilities), and **agent plugins** that select tools **from that metadata**—not a second, hand-maintained list of every function name.

Today that split is implemented in:

- Tool metadata: each tool module under `plugins/tools/` (loaded by `apps/backend/domain/plugin_system/registry.py`).
- Agent allowlists: each file under `plugins/agents/*.py`, resolved in `apps/backend/domain/agent_registry.py` (`get_agent`).

## Adding a new tool (author checklist)

Set on the **tool module** (same file as `HANDLERS` / `TOOLS`):

| Field | Required? | Role |
|--------|-----------|------|
| `TOOL_DOMAIN` | **Strongly yes** | Lowercase string, e.g. `coding`, `rag`, `operator`. The registry stores it on `tools_meta`; agents can allow **whole domains** via `AGENT_TOOL_DOMAINS`. Use `shared` only for truly cross-cutting tools. |
| `TOOL_CAPABILITIES` | Recommended | Package-wide capability strings (see `docs/adr/0002-tool-capabilities-convention.md`). The registry builds `capability_index`; agents can allow via `AGENT_TOOL_CAPABILITY_ANY`. |
| `AGENT_TOOL_META_BY_NAME` | Optional | Per-function overrides (`capabilities`, `min_role`, …). |

**Practical rule:** pick a `TOOL_DOMAIN` that matches the **agent persona** that should see the tool by default (e.g. all workspace file tools → `coding`). If one package exports both “coding” and “explain” style tools, split modules or use per-tool meta so an agent can target **capabilities** instead of a broad domain.

## Adding a new agent (`plugins/agents/<name>.py`)

Export the usual `AGENT_*` fields, then choose **how** tools are selected (see `agent_registry.py`):

1. **`AGENT_TOOL_DOMAINS`** — union of all tools whose package `domain` is in the tuple **or** `shared`. Best when a whole vertical shares one domain (e.g. coding workspace: `("coding", "project")`).
2. **`AGENT_TOOL_CAPABILITY_ANY`** — union of tools whose **effective** capability matches **any** listed string. Best for admin/operator surfaces (e.g. `operator.console`, `scheduler.job.read`).
3. **`AGENT_TOOL_PATTERNS`** — glob / `prefix.*` / exact names; use when domains would pull in too much (typical for a wide “general” assistant) or for one-off extras.
4. **`AGENT_TOOL_INCLUDE_INTROSPECTION`** — if you use domains and still need `list_available_tools` / `get_tool_help` etc. (those live in packages that may not set `TOOL_DOMAIN` the way domain-filter expects).

Resolution is the **union** of (2)+(3)+(4) when no explicit names list is used.

**Override:** non-empty **`AGENT_TOOL_NAMES`** replaces dynamic resolution (hard allowlist only).

## Optional chat-loop behaviour (no hard-coded agent ids)

`apps/backend/domain/agent.py` reads these **optional** module-level fields from each agent plugin (defaults are false / unset). They are stored on the registry dict and drive workspace gates, permission-ask, identical-call dedupe, and the extra tool-discipline system snippet:

| Field | Default | Role |
|--------|---------|------|
| `AGENT_STRICT_WORKSPACE` | `False` | If true, chat fails when no **resolved** project workspace is available (even when `AGENT_REQUIRES_WORKSPACE` is also true on other agents that allow auto-create). |
| `AGENT_CODING_TOOLS_PERMISSION_ASK` | `False` | If true and the client sets `agent_permission_ask`, gated `coding_*` write/bash/patch tools may require a WebSocket `permission_reply` before running. |
| `AGENT_DEDUPE_IDENTICAL_TOOL_CALLS` | `False` | If true, identical tool+JSON-args repeats in one reply are short-circuited with a dedupe message (loop hygiene). |
| `AGENT_TOOL_DISCIPLINE_PRESET` | unset | If set to a known preset string, appends the matching discipline block: `coding_plan`, `coding_build`, `security_auditor`. Otherwise the generic tool-usage discipline applies. |

Preset strings map to snippets in `agent.py` (`_TOOL_DISCIPLINE_BY_PRESET`). Add a new preset there **only** when you introduce a new discipline text; new agents otherwise reuse an existing preset key.

## Why this helps a future orchestrator

An orchestrator (top-level “router” agent) does not need a duplicate manifest of every tool name if tools already declare **`TOOL_DOMAIN`** and **`TOOL_CAPABILITIES`**. It can:

- Route a user intent to a **worker agent_id** + optional **capability hints** (already supported in chat via `agent_capability_hints` in the planner path), and/or
- Choose a downstream agent whose **`AGENT_TOOL_DOMAINS` / `AGENT_TOOL_CAPABILITY_ANY`** align with the same metadata.

So: **declare domain + capabilities on the tool once**; agents and future orchestration **subscribe** to slices of that space.

## Current built-in examples

- **Coding / Coding (plan) / Security auditor:** `AGENT_TOOL_DOMAINS = ("coding", "project")` (+ optional `AGENT_TOOL_CAPABILITY_ANY`); plan and security auditor set `AGENT_STRICT_WORKSPACE`, `AGENT_CODING_TOOLS_PERMISSION_ASK`, `AGENT_DEDUPE_IDENTICAL_TOOL_CALLS`, and `AGENT_TOOL_DISCIPLINE_PRESET` as needed (see table above).
- **Operator:** `AGENT_TOOL_CAPABILITY_ANY` in `plugins/agents/operator.py`; admin handlers live in `plugins/tools/agent/core/operator_admin.py` with `TOOL_DOMAIN = "operator"` and `operator.console` on each function.
- **General:** `AGENT_TOOL_PATTERNS` in `plugins/agents/general.py` (broad catalog; domain-only would mix unrelated `meta` tools without finer splits).

## See also

- `docs/adr/0001-tool-and-agent-architecture.md` — layers, capability index.
- `docs/adr/0002-tool-capabilities-convention.md` — naming capabilities.
- `docs/adr/0006-chat-secret-ingress-pipeline.md` — optional chat → vault → placeholders for operator apply (proposed).
- `apps/backend/domain/plugin_system/tool_routing.py` — `filter_merged_tools_by_domain`, router categories.
- `docs/features/operator-agent.md` — operator persona and admin tools.
