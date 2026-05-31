---
doc_id: tools-domains
domain: agentlayer_docs
tags: [tools, registry, agents, domains]
---

## Pattern

| Field | Meaning | Example |
|-------|---------|---------|
| **Folder** | Where code lives (navigation) | `integrations/mail/providers/gmail/` |
| **`TOOL_DOMAIN`** | Function — agent allowlist bucket | `mail`, `workspace` |
| **`TOOL_PROVIDER`** | Brand/backend implementation | `gmail`, `outlook` |
| **`TOOL_CAPABILITIES`** | Fine permissions | `mail.read`, `workspace.read` |

Agents use `tool_domains` + `tool_capability_any` in `plugins/agents/*/agent.yaml` — never hard-coded tool name lists.

Regenerate inventory: `python scripts/list_tool_domains.py --agents`

See **Phase 1 migration:** `docs/planning/tools-folder-phase1.md`

## Domain list (after phase 1)

| Domain | Role |
|--------|------|
| `repository` | Bound-repo file ops, shell, search, LSP, in-turn `todo` |
| `workspace` | Workspace bind / list / create only |
| `mail` | Email read/search (provider via `TOOL_PROVIDER` + user secret) |
| `github` | Git + GitHub API |
| `delegate` | Agent handoff + coding `task` |
| `project` | Repo explain, runs |
| `agent_tasks` | OS task queue (`task_create`, …) |
| `tasks` | Dashboard todo **boards** (persisted) |
| `dashboard`, `shopping`, `pets`, `ideas`, `rss`, `calendar` | Personal UI verticals |
| `kb`, `memory`, `rag` | Knowledge |
| `secrets`, `tool_help`, `operator`, `scheduler` | Platform |

Do **not** use agent names (`coding`), orchestration labels (`subagent`), or brands (`gmail`) as `TOOL_DOMAIN`.

Orchestrator discovery: **`catalog`** tool (`meta.agents.read` on general) — agent summary with domains/capabilities; full tool lists admin-only via `include_tool_names=true`.
