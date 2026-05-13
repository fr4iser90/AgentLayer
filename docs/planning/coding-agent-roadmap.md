---
doc_id: planning-coding-agent-roadmap
domain: agentlayer_docs
tags: [planning, coding-agent, security, backlog, git]
---

## Purpose

Single place for **how we extend the coding agent** without a huge upfront design doc: security invariants first, then **thin vertical slices** (one shippable increment at a time). Use this page to park ideas; track execution in issues or `docs/TODO-future.md` where appropriate.

Related docs:

- `docs/features/coding-workflow.md` — container/workspace workflow and validation expectations
- `docs/features/workspaces.md` — workspace model and sharing (update paths if the tree moves)
- `docs/TODO-future.md` — broader product/research backlog
- `docs/adr/0001-tool-and-agent-architecture.md` — tool loop architecture
- **`docs/adr/0005-agentlayer-self-workspace-contract.md`** — **binding contract** for AgentLayer-on-AgentLayer (self) workspace: DB id, rw path, seed rules

## Principles

1. **Same agent core, different clients** — planner loop stays in `apps/backend/domain/agent.py::chat_completion`; HTTP (`POST /v1/chat/completions`), WebSocket (`apps/backend/api/chat_websocket.py`), and bridges all call the same function.
2. **Do not boil the ocean** — capture all ideas briefly here; implement **one slice** at a time (e.g. read-only Git before push).
3. **Security is not “later”** — every new capability (Git, shell, background jobs) must state which invariants it preserves (see below).
4. **Professional by default** — one clear contract per feature (paths, IDs, read vs write); docs and `compose.yaml` match what the backend does; no “works on my laptop” surprises for the next contributor.

## Professionalization (hygiene, not heroics)

“Dirty” here means **accidental complexity**: two behaviors for the same thing, dead paths, or docs that describe a different layout than production. Tighten these deliberately (small PRs are fine).

### Self-workspace (AgentLayer-on-AgentLayer) — **contract locked**

**Source of truth:** [`docs/adr/0005-agentlayer-self-workspace-contract.md`](../adr/0005-agentlayer-self-workspace-contract.md).

Summary: self-workspace is a **normal DB workspace** (`name = agentlayer-self`), **`workspace_id` = row UUID** everywhere (chat, API). Files live under **`{AGENTLAYER_WORKSPACE_PATH}/{user_id}/agentlayer-self`** (read-write). **`/workspace/AgentLayer`** is **seed only** (may be read-only). The string **`__agentlayer_self__`** is **deprecated** for clients; implementation may still accept it temporarily during migration.

Until code matches this ADR, treat behavior as **in transition** and prefer explicit git/manual workspaces for demos.

### Durable workspace storage

Default workspace dirs live under `AGENTLAYER_WORKSPACE_PATH` (default `/workspace/...`). In Docker, that is **ephemeral** unless you mount a **named volume** (or host path) there. Document the **required** compose/env for any environment where work must survive restart.

### Docs aligned with reality

Keep **one** canonical story for “where does the coding agent run?” (`docs/features/coding-workflow.md`, this file, and comments in `compose.yaml`). If `/code` is only a ro mount for inspection and real edits go through DB workspaces, say so explicitly.

### Optional “pro” layer (later)

Structured **audit logs** (who deleted a workspace, who ran push, long `coding_bash`), and **CI** as the gate for “green” before anyone talks about deploy — see epic E.

## Security invariants (multi-user)

These should stay true regardless of UI. Code pointers are the source of truth.

| Invariant | Where it lives (today) |
|-----------|-------------------------|
| Coding file ops stay under a configured root; blocklist for dangerous prefixes | `apps/backend/core/config.py` — `CODING_ROOT`, `CODING_PATH_BLOCKLIST`, `CODING_MAX_FILE_BYTES`, `CODING_ENABLED` |
| Tools can be disabled, role-gated, tenant-scoped, host vs container | `apps/backend/domain/plugin_system/tool_policy.py`, `apps/backend/domain/plugin_system/tools.py::run_tool` |
| Chat runs with identity + optional workspace in tool context | `apps/backend/domain/agent.py::chat_completion` (`tool_context`: `workspace`, `user`) |

**Explicit gap to close over time:** every request that carries `workspace_id` must be **authorized** server-side (membership / ownership), not only hidden in the UI. Treat that as an ongoing epic, not a one-off.

## Epics (suggested order)

Order is **recommended**, not a promise. Each epic should ship something testable before the next.

### A — Workspace authorization hardening

- Server-side checks: caller may use this `workspace_id` for chat/coding tools.
- Align with sharing rules documented under workspaces (see `docs/features/workspaces.md`).
- Add regression tests for “wrong user / wrong workspace” cases.

### B — Git integration (staged)

1. **Read-only:** status, log, diff, current branch (low risk, high value).
2. **Local writes:** commit inside sandbox with clear rules (message, scope).
3. **Network:** fetch/push/PR — separate design: credentials, egress, rate limits, audit.

### C — Tasks and follow-ups (product)

- Lightweight task list or links from chat/thread to “open work” (can start as UI + stored JSON before full automation).
- Optional: export to external tracker later.

### D — “Background planner” (later)

Ideas such as: idle time → model drafts **several** plans → user picks one → agent runs tests — **high complexity** (cost, permissions, UX, storage of drafts). Defer until A + B (read path) feel solid. Smaller stepping stone: **explicit** “suggest plans” action with a single round-trip and a token budget.

### E — Testing in the loop

- Define what “agent must run before done” means per stack (lint, typecheck, unit tests) — `docs/features/coding-workflow.md` already states this as a rule of thumb.
- Prefer **one** canonical command per repo kind (or per workspace config) rather than ad-hoc shell.

### F — Self-workspace + ops alignment (professional default)

- **Done (ADR 0005 backend):** `workspace_service` materializes rw copy + DB UUID; resolver DB-only; chat loads real user role; list API returns self row like others; reserved name `agentlayer-self` on `POST /v1/workspaces`.
- **Done (ops):** `compose.yaml` uses named volume `agent_project_workspaces` + `AGENTLAYER_WORKSPACE_PATH=/data/project_workspaces`; runbook `docs/runbooks/workspace-persistence.md`.
- After deploy, smoke-test: create workspace → write file → `docker compose restart agent-layer` → file still there.

## ADRs: iterative, not a catalog upfront

During a **“big rebuild + many ideas”** phase, **do not** try to write or “fix” a complete set of ADRs for every module before shipping. You risk spending weeks on documents that go stale or encode guesses.

**When an ADR is worth it**

- The choice is **hard to reverse**, expensive to change later, or crosses a **security / tenancy** boundary.
- **Two or more** reasonable options exist and you need a **single** team answer (e.g. ADR 0005 for self-workspace).
- Onboarding or compliance needs a **stable** statement of “why it is this way.”

**What to do instead for the rest**

- Keep a **rough problem-space list** (vision, gaps, questions) in this roadmap or `docs/TODO-future.md` — **no decision** required yet.
- Promote to an ADR only when you are about to **implement** or **lock** that slice.

**Example problem spaces** (collect as bullets/issues; ADR only when you decide)

Agent runtime, memory, tools, workflows/scheduler, permissions/security, multi-agent comms, web UI, deployment, events, plugins, observability, MCP, local vs cloud LLM, queues, scheduling, indexing/RAG/embeddings — many of these already have partial docs or ADRs (0001–0004); fill gaps **when that area is in active work**, not all at once.

## How to use this doc day to day

- **New idea:** add a bullet under the right epic (or a new `###` epic if it is a new theme).
- **Ready to build:** open an issue or task with acceptance criteria + which invariant it touches.
- **Done:** remove or check off in your tracker; optionally add a one-line “Implemented in …” note here if it helps RAG and onboarding.

## Git notes (when you start epic B)

- Prefer **porcelain commands** or a small library with structured output; avoid parsing fragile human-only text.
- Never pass unchecked remote URLs or refspecs from the model straight to shell without validation.
- Log **who** triggered **what** Git action on **which** workspace for audit trails.
