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
- **`apps/backend/domain/workspace/resolver.py`:** `resolve_workspace` is **DB-only** (no magic self id).
- **`apps/backend/domain/agent.py`:** Loads DB user (real `role`) before `ensure_workspace` so self-editing gates apply correctly.
- **`apps/backend/api/workspaces_api.py`:** `_get_self_workspace` returns the same list JSON shape as other workspaces; `POST /v1/workspaces` rejects reserved name `agentlayer-self`.

**Ops:** see `compose.yaml` (`agent_project_workspaces`, `AGENTLAYER_WORKSPACE_PATH`) and `docs/runbooks/workspace-persistence.md`.

## Amendment (2026-09-20): the seed copy must not swallow its own destination

Found live on a self-hosted deployment. The v1 rule above — *"copy is still
allowed from ro into rw target"* — was written without considering that the
rw target can live **inside** the ro seed. With the shipped compose layout
(`.:/workspace/AgentLayer:ro` and `./workspace:/data/project_workspaces:rw`),
`AGENTLAYER_WORKSPACE_PATH` is bind-mounted from a host directory that sits
inside the repo used as the seed. A plain `shutil.copytree(seed, target)`
therefore copies the destination into itself and recurses until
`ENAMETOOLONG`. Because the copy runs in the request path, the instance
stopped answering entirely and did not recover on its own.

Two further problems in the same copy: it dragged `output/` (1.8 GB on that
box), `node_modules` and caches into every user workspace, and it copied
`.env` where the coding agent could read it.

Fixed in `workspace_service._seed_copy_ignore`, applied at both copy sites:

* The workspace base is detected by **`(st_dev, st_ino)`**, not by path
  string. A bind mount shares identity with its host directory, so this
  catches the nesting regardless of directory names — and a textual
  containment check cannot, because inside the container
  `/workspace/AgentLayer` and `/data/project_workspaces` look unrelated.
* Regenerable artifacts are excluded: `node_modules`, `venv`/`.venv`,
  `__pycache__`, `.pytest_cache`, `.mypy_cache`, `.ruff_cache`, `output`,
  `.scanning`.
* **`.git` is deliberately kept.** The self-workspace must remain a git
  checkout — `workspace_git.py` and the repo-status path refuse a tree with
  no `.git`, so excluding it would break the feature it belongs to.

Verified live: materialization returns promptly and the tree is 73 MB with
no self-nesting and no leaked artifacts. Guarded by
`tests/unit/test_self_workspace_seed_copy.py`, whose negative control
reproduces the recursion when the ignore filter is absent.

## Open point: explicit git seed (not implemented)

The v1 text already anticipated a git-based seed ("*git checkout preferred
when we add explicit git seed*"). It is still open, and the deliberate
position is that **a remote clone is not automatically the better default
source**: the initial workspace should represent the code that is
**actually running**, including uncommitted local changes. A clone from the
remote can diverge from the deployed version and from the operator's local
work, which is exactly what self-editing is meant to operate on.

If added, it should be a **configurable alternative**, not a replacement —
an explicit self-repo URL + branch + credential, reusing the existing
shallow-clone-with-retries path in `workspace_git_clone.py`, with the local
seed remaining the default. `agentlayer-self` rows are created
`source='manual', git_url=NULL` today, which reflects that choice.

## Related

- `docs/planning/coding-agent-roadmap.md` — epic F, professionalization section
- `docs/runbooks/workspace-persistence.md` — Docker volume + path changes
- `apps/backend/domain/workspace/resolver.py`, `apps/backend/infrastructure/workspace_service.py`, `apps/backend/api/workspaces_api.py`, `apps/backend/domain/agent.py`
