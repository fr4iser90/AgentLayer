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

### G — Agentic coding parity (industry-style UX)

**Goal:** match the *product* expectations of terminal-first coding agents: reliable tools, read→plan→act, strong search, optional subagents, observable runs. **Full checklist and phased plan:** [Agentic coding: checklist and phased plan](#agentic-coding-checklist-and-phased-plan) (end of this doc).

### H — Subagents & delegation

**Goal:** explore/search/plan in isolated context without polluting the main planner transcript; merge results back with citations. **Design options and milestones:** same anchor section under *Subagents*.

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

---

## Agentic coding: checklist and phased plan

Single backlog derived from “what agentic coding needs in general,” mapped to AgentLayer today and **ordered slices** (ship one vertical increment per PR where possible). Epics **G**/**H** in the table above point here.

### Checklist (Baustein → Zweck → Stand AgentLayer)

| Baustein | Zweck | AgentLayer (Stand / nächster Schritt) |
|----------|--------|--------------------------------------|
| **Workspace / Cwd** | Eindeutiger Baum für alle Coding-Tools | **Habt ihr:** `workspace_id`, Clone, `coding_*` mit Root. **Next:** UI immer sichtbarer Workspace-Pfad; Auth-Härtung (Epic A). |
| **Zuverlässige Tool-JSON** | Keine Endlosschleifen (`coding_bash({})`) | **Teilweise:** Server-Normalisierung, Rescue-/letzte Text-Runde. **Next:** Circuit-Breaker (gleicher Tool-Name + gleiche leere Args 2× → System-Nudge oder Text-only); optional zweites LLM nur für Tool-JSON; weiter Modell-Routing-Docs. |
| **Read → Plan → Act** | Weniger blindes Editieren | **Habt ihr:** `coding_plan` Agent + Registry-Allowlist (read/meta only); UI wählt Agent. **Next:** Auto-Routing erste N Runden optional. |
| **Patch-first Editing** | Stabilere Edits | **Habt ihr:** `coding_apply_patch`, replace, edit. **Next:** Prompt/Default „prefer patch“; Metriken ob Patch vs. full write. |
| **Schnelle Suche** | Repo ohne 20× `list_dir` | **Habt ihr:** `coding_search`, `coding_glob`, Index/Qdrant optional; bei Cap **`truncation_hint`** im JSON. **Next:** Ripgrep-Pfad in Container, Index-on-open optional. |
| **LSP / Diags** | Echter Code-Intellekt | **Habt ihr:** `coding_lsp`. **Next:** Image/PATH-Doku, pro-Sprache Smoke, Fehler in Tool-Result klar surfaced. |
| **Tests/Linter im Loop** | „Fertig“ definiert | **Teilweise:** optional `verify_command` / `note` in Workspace-Root **`.agentlayer.json`** (Hinweis im ersten System-Prompt; kein Auto-Run). **Next:** explizites Ausführen vor „done“; CI-Webhook (Epic E). |
| **Budgets** | Tokens, Runden, Zeit | **Habt ihr:** `AGENT_MAX_TOOL_ROUNDS`, Rescue. **Next:** pro-Agent-Override, UI-Warnung bei niedrigem Budget. |
| **User-Memory vs Thread** | Langzeit vs. Session | **Habt ihr:** Facts/Notes/Graph + `messages`; **Session tool recap** nach Tool-Blöcken (`AGENT_SESSION_TOOL_RECAP_*`). **Next:** komprimierte inhaltliche Zusammenfassung (nicht nur Tool-Namen). |
| **Observability** | Debuggen | **Teilweise:** Logs, `agent.session`. **Next:** Trace-ID pro Run, strukturierte Tool-Fehler in Events, optional Export. |
| **Subagents** | Explore/Plan isoliert | **Teilweise:** `coding_task` mit **`run_plan_subagent=true`** → gebundener `coding_plan`-Lauf im Side-Thread (`chat_completion`, gleiches `workspace_id`). **Next:** UI-Summary, Cancellation, Accounting. |

### Phased rollout (recommended order)

Each phase should end with **manual smoke** + **one paragraph** in this doc or ADR pointer if a security/tenancy boundary moved.

#### Phase 1 — Tool reliability & loops (highest ROI)

**Implemented (baseline):**

- Circuit-breaker in `apps/backend/domain/agent.py`: identical JSON tool failures (`ok: false` + same `error` prefix per tool name) for `AGENT_TOOL_THRASH_STREAK_MAX` (default 3, min 2) → system hint one step before, then **one round without `tools[]`** (`AGENT_TOOL_THRASH_ENABLED`, `AGENT_TOOL_THRASH_STREAK_MAX` in `config.py` / `.env.example`).
- `agent.tool_done` WebSocket events optionally include `result_ok` (bool) and `result_error` (truncated string) when the result parses as JSON with an `ok` field.

**Still open / later slices:**

- Expand normalization only where safe (document rules); avoid silent dangerous `git`.
- Trace-ID pro Run; reichere strukturierte Events für die UI bei Bedarf.

**Exit (Phase 1):** dieselbe Tool-Fehlermeldung N-mal hintereinander → Hinweis, dann eine **Text-only-Runde** ohne `tools[]` (entspricht dem früheren „`coding_bash({})`-Schleifen“-Ziel).

#### Phase 2 — Plan vs Build (Read → Plan → Act)

**Implemented (baseline):**

- Agent **`coding_plan`**: Plugin `plugins/agents/coding_plan.py`, Eintrag in `agent-config.yaml`, Allowlist in `apps/backend/domain/agent_registry.py` (`AGENT_TOOL_MAP`) — read/meta coding tools only, **kein** `write` / `bash` / `apply_patch`.
- Berechtigung: wie **`coding`** (`agent:coding`), damit bestehende Rollen nicht brechen.

**Still open:** UI-Toggle bleibt Modellwahl; optionales Auto-Routing „erst N Runden Plan“.

#### Phase 3 — Search / Index / LSP polish

**Implemented (slice):**

- `coding_glob` / `coding_search`: bei Cap ein Feld **`truncation_hint`** mit konkreter Anweisung (narrower glob, `path_prefix`, Limits in Config).

**Still open:** Index-on-attach (Flag), LSP-Runbook pro Stack, optional Ripgrep.

#### Phase 4 — Verify-in-the-loop & session working memory

**Implemented (partial):**

- Workspace-Hinweis: **`{workspace}/.agentlayer.json`** mit optional `verify_command`, `note` → in ersten System-Kontext gemerged (Hinweis only; **kein** automatisches Ausführen).
- **Session tool recap:** nach Tool-Batches kurze `system`-Zeilen `[Session tool recap] …` (`AGENT_SESSION_TOOL_RECAP_ENABLED`, `AGENT_SESSION_TOOL_RECAP_MAX` in `config.py` / `.env.example`).

**Still open:** Verify-Command wirklich ausführen + Ergebnis einspeisen; inhaltliche Session-Zusammenfassung (LLM/truncator).

#### Phase 5 — Subagents & delegation (Epic H)

**Ziel:** Unter-Agent mit eigenem Nachrichten-/Budget-Kontext; Rückgabe als strukturiertes JSON / Auszug an den Haupt-Planner.

**Option A — Nested planner (gestartet)**  
- **`coding_task`** mit **`run_plan_subagent: true`**: `ThreadPoolExecutor` + `asyncio.run(chat_completion(...))` mit **`agent_id: coding_plan`**, gleiches **`workspace_id`**, konfigurierbare **`max_rounds`** (1–8) / **`subagent_model`**. Ergebnis: `assistant_excerpt` + Metadaten (Timeout 600s).
- Vorteil: wenig neue Infrastruktur. Nachteil: Kosten/Latenz; Cancellation/Accounting noch grob.

**Option B / C:** unverändert später (Queue, Prozess-Isolation).

**Milestone H1:** **teilweise erfüllt** (read-only Sub-Planner über Tool-Flag).  
**Milestone H2/H3:** offen (UI, Logs, Queue/Isolation).

### Memory & threading (explizit)

- **Thread:** immer `messages` aus dem Client; kein Ersatz durch User-Memory.
- **User memory:** nur wenn Operator `memory_enabled` und Inhalt in DB; Dashboard-ID für scoped Facts optional (`agent_dashboard_context`).
- **Working memory (neu, Phase 4):** kurzlebige, servergenerierte Zusammenfassung der *aktuellen* Agent-Session — nicht dasselbe wie `user_memory_facts`.

### Success metrics (pragmatisch)

- **Tool thrash:** median `get_tool_help` pro User-Request ↓; 0× identische leere Tool-Calls in Folge.
- **Task completion:** README-ähnliche Aufgaben enden mit `read_file` Erfolg oder erklärtem Blocker in ≤ X Runden (X messen, dann senken).
- **User trust:** UI zeigt Workspace + letzte harte Tool-Fehler sichtbar.

### Related code (jump table)

| Thema | Wo |
|--------|-----|
| Planner / Runden / Rescue | `apps/backend/domain/agent.py` |
| Tool args normalize | `apps/backend/domain/agent.py` |
| Workspace / clone | `apps/backend/infrastructure/workspace_service.py`, `workspaces_api.py` |
| Coding tools | `plugins/tools/capabilities/coding/` |
| Memory inject | `apps/backend/domain/agent.py::_inject_user_memory_context`, `apps/backend/api/memory.py` |
| Agent registry | `apps/backend/domain/agent_registry.py`, `plugins/agents/*.py` |
| Subagent / plan delegation | `plugins/tools/capabilities/coding/coding_task.py` (`run_plan_subagent`) |

---

When this plan moves to implementation, split into **issues per phase**; keep security invariants from the top of this doc in every PR description.
