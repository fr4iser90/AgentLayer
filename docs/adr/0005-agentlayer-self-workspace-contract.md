---
doc_id: adr-0005-agentlayer-self-workspace
domain: agentlayer_docs
tags: [adr, workspaces, coding-agent, self-workspace]
---

# ADR 0005: AgentLayer self-workspace contract (v1)

## Status

Accepted (contract). Implementation may lag; behavior should converge to this ADR, not the other way around.

## Context

“Self-workspace” (editing the AgentLayer repo from inside AgentLayer) had overlapping behaviors:

- A **magic id** `__agentlayer_self__` and resolver paths pointing at **`/workspace/AgentLayer`**, which in default **Docker Compose** is a **read-only** bind mount — coding tools that write then fail or confuse users.
- A **per-user copy** under `AGENTLAYER_WORKSPACE_PATH/{user_id}/agentlayer-self` and DB rows (`name = agentlayer-self`) in some code paths, but not wired consistently (e.g. unused helpers in `workspaces_api.py`).
- Chat and list potentially disagreeing on which **workspace_id** is authoritative.

We need **one** contract so docs, API, UI, and Compose expectations match.

## Decision (v1 contract)

### What “self-workspace” is

The **AgentLayer self-workspace** is a **normal `project_workspaces` row** owned by the user:

- **`name`:** exactly `agentlayer-self` (stable sentinel for discovery and UX).
- **`workspace_id` in API and chat:** the row’s **UUID** (same as any other workspace). Clients MUST NOT rely on `__agentlayer_self__` for new integrations.

The magic string **`__agentlayer_self__`** is **deprecated** for public API and chat payloads. It may remain temporarily as an internal alias during migration; new code MUST prefer the DB id.

### Where files live (read-write)

- **Root path on disk:** `{AGENTLAYER_WORKSPACE_PATH}/{user_id}/agentlayer-self` (default `AGENTLAYER_WORKSPACE_PATH` = `/workspace` unless overridden).
- This directory MUST be **read-write** from the agent process. Coding tools use `tool_context["workspace"]["path"]` as the tree root — that path MUST be this directory, **not** the read-only seed mount.

### How the tree is seeded (once, idempotent)

On **first materialization** (directory missing or empty policy TBD in implementation), the server copies from the **first available** source (git checkout preferred when we add explicit git seed; until then **recursive copy**):

1. **`/workspace/AgentLayer`** if it exists and contains a `.git` directory (typical compose seed; may be read-only — copy is still allowed **from** ro into rw target).
2. Else **`/app`** if it exists and contains `.git` (container checkout image layout).
3. Else: **do not** invent a repo — surface a clear **operator-visible** error (“no seed source for agentlayer-self”) and disable self-workspace for that deployment until configured.

Re-seed rules (v1): **no automatic overwrite** of an existing non-empty `agentlayer-self` tree without an explicit admin/user “reset” action (separate feature; out of scope for this ADR).

### Who may see or use it

Unchanged from existing product rules (must all remain true):

- Operator setting **`workspace_allow_self_editing`** enabled.
- User is **admin** OR has **`workspace_self_allowed`** on the user record.

If either check fails, the self-workspace row MUST NOT appear in listings and MUST NOT resolve for chat.

### Relationship to `/code` and `/workspace/AgentLayer` mounts

- **`/workspace/AgentLayer`** (and similarly **`/code`** in compose): **optional read-only inspection / seed** only for v1. They are **not** the canonical writable root for self-editing.
- Documentation and compose comments SHOULD state: **writable work happens under `AGENTLAYER_WORKSPACE_PATH/.../agentlayer-self`** (with persistence via volume when required).

### Persistence

Survival across container restarts requires a **Docker volume** (or host bind) covering `AGENTLAYER_WORKSPACE_PATH` (or the parent of per-user dirs). That is an **ops requirement**, not optional for “serious” self-editing; document in runbook / compose example (see roadmap epic F).

## Consequences

- **Frontend:** Coding agent should select the self-workspace by **UUID** from `GET /v1/workspaces` like any other workspace.
- **Migration:** Any stored conversations or bookmarks using `__agentlayer_self__` may keep using it; the server still accepts that alias in `ensure_workspace` until clients migrate.

## Implementation (backend)

- **`apps/backend/infrastructure/workspace_service.py`:** `self_editing_allowed`, `materialize_agentlayer_self_workspace`, `try_resolve_agentlayer_self_db`, `ensure_workspace` (legacy alias `__agentlayer_self__`). Seed: first of `/workspace/AgentLayer`, `/app` with `.git`. Writable tree: `{AGENTLAYER_WORKSPACE_PATH}/{user_id}/agentlayer-self`. Legacy DB rows with wrong `path` are updated on materialize.
- **`apps/backend/domain/workspace_resolver.py`:** `resolve_workspace` is **DB-only** (no magic self id).
- **`apps/backend/domain/agent.py`:** Loads DB user (real `role`) before `ensure_workspace` so self-editing gates apply correctly.
- **`apps/backend/api/workspaces_api.py`:** `_get_self_workspace` returns the same list JSON shape as other workspaces; `POST /v1/workspaces` rejects reserved name `agentlayer-self`.

**Ops:** see `compose.yaml` (`agent_project_workspaces`, `AGENTLAYER_WORKSPACE_PATH`) and `docs/runbooks/workspace-persistence.md`.

## Related

- `docs/planning/coding-agent-roadmap.md` — epic F, professionalization section
- `docs/runbooks/workspace-persistence.md` — Docker volume + path changes
- `apps/backend/domain/workspace_resolver.py`, `apps/backend/infrastructure/workspace_service.py`, `apps/backend/api/workspaces_api.py`, `apps/backend/domain/agent.py`
