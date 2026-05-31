---
doc_id: adr-0007-user-delegate
domain: agentlayer_docs
tags: [adr, delegate, autonomy, chat, workspace, persona]
---

# ADR 0007: User Delegate (Stellvertreter) — decision authority, not persona

## Status

**Accepted** — design for phased implementation. See [`docs/planning/user-delegate-roadmap.md`](../planning/user-delegate-roadmap.md).

## Context

Users want the product to **continue work without them** when they step away — e.g. after a security scan report and option list, the system should **decide and execute** (pull `main`, fix HIGH findings, suppress test noise) instead of waiting for another chat message.

This is **not** “make the assistant sound like me” (`user_agent_persona`, tone, vocabulary). It is:

> **An entity that may take decisions on the user's behalf**, within explicit goals and autonomy bounds.

Working names:

| Layer | Code | UI (DE) | UI (EN) |
|-------|------|---------|---------|
| Global | `user_delegate` | Stellvertreter | Delegate / User Delegate |
| Per workspace | `workspace_delegate` | Stellvertreter (Projekt) | Workspace Delegate |

Subtitle: *Handelt in deinem Namen, wenn Auto-Respond aktiv ist.* / *Acts on your behalf when autonomous actions are enabled.*

### Related existing concepts (do not conflate)

| Existing | Purpose | Delegate relationship |
|----------|---------|------------------------|
| `user_agent_persona` / `user_agent_profile` | Agent tone & structured profile for **normal** chat injection | Orthogonal; may overlap in wording but **different API and semantics** |
| User memory (facts, notes, graph) | Opt-in retrieval context | May **inform** delegate decisions; not authoritative for autonomy |
| `agent_tasks` (`goal`, `requirements`) | Backlog + conversation binding | **Task goal** feeds delegate decision for active work |
| `coding_schedule_execution` | Unattended runs (`agent_unattended`, no permission UI) | **Reuse** merge + autonomy rules for scheduled jobs |
| `json-proposal` in chat | User clicks an option | Auto-Respond **replaces** waiting; delegate LLM decides instead of mechanical “option 1” |

## Problem statement

1. **Interactive chat is turn-based** — every assistant message waits for human input.
2. **Agents are trained to ask** — proposals, confirmations, `security_auditor` report-first behavior.
3. **“Learn my persona from chat” drifts** — context-dependent behavior becomes contradictory rules (vacation vs crunch week; one-off rushed replies stored as permanent prefs).

Two product goals must stay **separate**:

| Goal | Description | Risk |
|------|-------------|------|
| **G1 Auto-Respond** | Idle timeout → delegate decides → agent continues | Wrong automation — mitigated by caps and audit |
| **G2 Long-term alignment** | System suggests delegate config updates over months | Drift — mitigated by **observe → suggest → user confirms** |

## Goals

| ID | Goal |
|----|------|
| G1 | Persist **explicit** global and workspace delegate configuration (structured JSON, user-authored defaults). |
| G2 | **Auto-Respond** in chat: after *N* seconds without human input, run a **delegate decision** step and continue the agent loop. |
| G3 | Delegate acts on **stable goals and autonomy flags**, not voice mimicry. |
| G4 | **Audit** every delegated run (`delegate_run_id`, link to `agent_run_id`, visible `[Stand-in · auto]` in UI). |
| G5 | **Hard limits** on autonomous chains (turn count, wall time, daily cap, denied actions). |
| G6 | Optional learning: **observations** never auto-merge; **suggestions** require explicit accept. |

## Non-goals

- Impersonating the user in chat without disclosure (no hidden `role: user` without marker).
- Silent overwrite of delegate config from chat transcripts.
- Replacing scheduler jobs — delegate is a **shared decision config**; schedulers remain a separate trigger.
- Full behavioral cloning / “always reply exactly like user”.

## Decision

### 1) Delegate config shape (explicit identity)

Store validated JSON on:

- **`user_delegate`** — one row per user
- **`workspace_delegate`** — one row per `project_workspaces.id`

Recommended top-level keys:

```yaml
communication:   # how much to explain, not literary style
engineering:     # security_first, prefer_tests, …
autonomy:        # can_merge_prs, can_force_push, can_fix_minor_issues, …
goals:           # stable intent list (strings)
notes:           # optional short free text (capped)
```

**Merge rule:** For the same key path, **workspace overrides global**. Inject merged **goals + engineering + autonomy** into delegate decision and (optionally) unattended agent system blocks — not the entire raw chat history into persona storage.

Size caps (initial): ≤ 8 KiB global config, ≤ 4 KiB workspace config (serialized JSON).

### 2) Auto-Respond flow

```
[Assistant finishes turn; user idle ≥ N sec; auto-respond enabled]
        ↓
[Build context: tail messages, active task, scan state, merged delegate]
        ↓
[Delegate decision LLM — tools OFF]
  Output: decision_summary + synthetic_user_message
        ↓
[Append user message (marked) OR direct unattended chat_completion]
        ↓
[Agent executes with agent_unattended + permission_ask false when policy allows]
        ↓
[delegate_runs audit row + agent_run_id]
```

**Decision prompt principle:** *Handle according to delegate goals and autonomy; do not ask the user; do not emit json-proposal.*

Variant **A (MVP):** API returns synthetic user text → client sends normal agent turn (same as proposal option click).  
Variant **B:** Server runs full `chat_completion` (works when browser closed).

### 3) Learning model (phased — not v1)

| Layer | Table / concept | In prompt? |
|-------|-----------------|------------|
| Explicit config | `user_delegate`, `workspace_delegate` | Yes (merged) |
| Observations | `delegate_observations` | **No** |
| Suggestions | `delegate_suggestions` | Only after user accept → updates config |
| Decision examples | Optional retrieval (Phase 5) | Top-K when similar situation |

Pattern mirrors **`memory_graph_propose`** (propose → apply), not **`dynamic_traits`** auto-injection without review.

### 4) Limits (mandatory for G1)

- `delegate_max_chain_turns` per conversation (default 3)
- Respect existing `agent_max_tool_rounds`
- Wall-clock timeout per chain (e.g. 20 minutes)
- Stop on denied autonomy (push, merge, force-push)
- Optional operator/user daily cap on delegate-triggered runs

### 5) UI & transparency

- Chat: checkbox **Auto-Respond** + delay seconds
- Synthetic / delegated content labeled **`[Stand-in · auto]`** (DE) / **`[Delegate · auto]`** (EN)
- Settings: **Stellvertreter** page for global config; workspace editor on project
- Activity log: recent `delegate_runs`

### 6) API (minimum)

| Method | Path | Purpose |
|--------|------|---------|
| GET/PUT | `/v1/user/delegate` | Global config |
| GET/PUT | `/v1/workspaces/{id}/delegate` | Workspace overlay |
| POST | `/v1/user/conversations/{id}/delegate-respond` | Idle trigger → decision + optional execute |
| GET | `/v1/user/delegate/runs` | Audit log |
| GET/PATCH | `/v1/user/delegate/suggestions` | Phase 4 inbox |

Extend conversation PATCH with `delegate_auto_respond_enabled`, `delegate_auto_respond_after_sec`.

### 7) Integration points (later phases)

- **`coding_schedule_execution`:** prepend merged workspace delegate goals to job system prompt
- **`agent_tasks`:** active task `goal` / `requirements` in delegate context
- **Operator kill-switch:** `operator_settings.delegate_enabled`

## Alternatives considered

| Alternative | Rejected because |
|-------------|------------------|
| Extend `user_agent_persona` | Wrong semantics; conflates “how agent talks” with “who may decide” |
| Auto-pick highest-confidence `json-proposal` option | No real judgment; wrong for nuanced security/remediation |
| Full chat persona learning | Drift, false positives from one-off messages |
| Only scheduler (no chat idle) | Does not solve mid-conversation stall after scan report |

## Consequences

**Positive**

- Clear product story: **Stellvertreter** = delegated authority
- Reuses unattended execution patterns from scheduler
- Safe evolution path for learning (suggestions inbox)

**Negative / cost**

- New tables, APIs, settings UI, and chat timer logic
- Must keep delegate merge, task goals, and agent prompts consistent
- Operators need caps to prevent runaway automation

**Migration**

- No change to existing persona/profile rows
- New migration `schema_065+` (see roadmap)

## Implementation phases

| Phase | Deliverable |
|-------|-------------|
| P0 | Schema, API, settings UI, merge helper, tests |
| P1 | Auto-Respond MVP + audit + limits |
| P2 | Scheduler + task context integration |
| P3 | Observations (passive) |
| P4 | Suggestions inbox |
| P5 | Decision examples (retrieval) |

Full checklist: [`docs/planning/user-delegate-roadmap.md`](../planning/user-delegate-roadmap.md).

## References

- `apps/backend/domain/user_persona.py` — existing persona (separate concern)
- `apps/backend/infrastructure/coding_schedule_execution.py` — unattended agent pattern
- `apps/backend/infrastructure/agent_tasks_store.py` — task goals
- `docs/features/memory.md` — memory graph propose/apply pattern
- `plugins/agents/general.py` — `json-proposal` (auto-respond bypasses waiting, not necessarily the format)
