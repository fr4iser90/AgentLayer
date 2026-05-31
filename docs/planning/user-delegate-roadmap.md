# User Delegate / Stellvertreter — implementation roadmap

English implementation backlog; product copy is bilingual (DE **Stellvertreter**, EN **Delegate**).

**Related:** [ADR 0007: User Delegate](../adr/0007-user-delegate.md)

---

## What this is (and is not)

| Concept | Meaning |
|---------|---------|
| **User Delegate** | Entity that may **decide and act on the user's behalf** when autonomous actions are enabled — not “how the assistant talks”. |
| **Workspace Delegate** | Project-specific overlay (goals, autonomy caps, engineering priorities). |
| **Auto-Respond** | Trigger: no human input for *N* seconds → delegate decides → agent continues. |

**Not the same as:**

- `user_agent_persona` / `user_agent_profile` (agent tone & context for normal chat)
- Memory facts/notes (retrieval layer; may **inform** delegate but does not replace explicit delegate config)
- Scheduler jobs (separate trigger; should **reuse** delegate merge logic later)

**Product subtitle (DE):** *Handelt in deinem Namen, wenn Auto-Respond aktiv ist.*  
**Product subtitle (EN):** *Acts on your behalf when autonomous actions are enabled.*

---

## Two goals — build in this order

| # | Goal | Risk | Phase |
|---|------|------|-------|
| 1 | **Auto-Respond** — delegate decides when user is idle | Medium (wrong fixes) — mitigated by caps + audit | **P0–P2** |
| 2 | **Become more like the user over time** | High (drift, false generalization) | **P3+** only via observe → suggest → confirm |

Never allow the system to **silently overwrite** `user_delegate` / `workspace_delegate` from chat behavior alone.

---

## Data model (target)

### `user_delegate` (1 row per user)

Structured JSON (validated schema), e.g.:

```yaml
communication:
  directness: high
  detail_level: medium
  ask_before_major_changes: true
engineering:
  security_first: true
  prefer_tests: true
  prefer_refactoring: false
  primary_goal: stability
  priorities: [security, stability, maintainability, speed]
autonomy:
  can_fix_minor_issues: true
  can_merge_prs: false
  can_force_push: false
decisioning:
  risk_tolerance: low
escalation:
  ask_on_production_changes: true
  ask_on_database_migrations: true
  ask_on_security_findings: false
goals:
  - keep projects stable
  - reduce manual toil
```

Defaults: `DEFAULT_USER_DELEGATE_CONFIG` / `DEFAULT_WORKSPACE_DELEGATE_CONFIG` in `delegate_config_schema.py` (workspace scope: `risk_tolerance` defaults to `medium`).

Optional free-text `notes` (short, capped).

### `workspace_delegate` (1 row per `project_workspaces.id`)

Same shape subset + workspace-specific `goals`, `engineering`, `autonomy`. **Workspace wins** on conflict with global for scoped keys.

### `delegate_observations` (append-only, passive)

Counters / events — **never injected** into prompts automatically:

```yaml
- kind: user_requested_tests
  count: 17
  workspace_id: null | uuid
  last_seen_at: ...
```

### `delegate_suggestions` (inbox)

LLM- or rule-generated proposed patches to delegate JSON; status `pending | accepted | rejected`.

### `delegate_runs` (audit)

Each auto-respond / delegated execution: trigger, merged config snapshot hash, decision text, synthetic user message (if any), `agent_run_id`, duration, outcome.

### Conversation prefs (extend `chat_conversations` or composer prefs)

- `delegate_auto_respond_enabled` (bool, default false)
- `delegate_auto_respond_after_sec` (int, e.g. 30–300)
- `delegate_max_chain_turns` (int, per conversation session cap)

---

## Phase P0 — Foundation (schema + API + settings UI)

### P0.1 Database

- [x] Migration `schema_067_user_delegate`:
  - [x] `user_delegate` (`user_id`, `tenant_id`, `config JSONB`, `notes TEXT`, `updated_at`)
  - [x] `workspace_delegate` (`workspace_id`, `tenant_id`, `config JSONB`, `updated_at`)
  - [x] Unique constraints + FK to `users` / `project_workspaces`
- [x] JSON schema validation module `apps/backend/domain/delegate_config_schema.py` (max sizes, allowed keys)
- [x] Caps: total serialized config ≤ 8 KiB global, ≤ 4 KiB workspace (tunable)

### P0.2 Backend store + API

- [x] `apps/backend/infrastructure/user_delegate_store.py` — get/upsert
- [x] `apps/backend/infrastructure/workspace_delegate_store.py` — get/upsert (workspace access check)
- [x] `GET` / `PUT` `/v1/user/delegate`
- [x] `GET` / `PUT` `/v1/workspaces/{workspace_id}/delegate`
- [x] Merge helper `build_delegate_context_block()` in `delegate_merge.py`

### P0.3 Settings UI

- [x] New settings page **Stellvertreter** / **Delegate** (`DelegateSettings.tsx`)
- [x] Structured form (communication / engineering / autonomy / goals)
- [x] Link from Agent settings (*Persona vs Delegate*)
- [x] i18n in `locales/{de,en}/settings.json`
- [x] Workspace delegate editor (workspace picker on delegate page)

### P0.4 Documentation

- [x] ADR 0007
- [x] This roadmap
- [x] `docs/features/user-delegate.md` (user-facing stub; expand with Auto-Respond in P1)

### P0.5 Tests

- [ ] `tests/test_user_delegate_api.py` — CRUD, validation, 403 foreign workspace (integration)
- [x] `tests/test_user_delegate.py` — validation + merge rules

---

## Phase P1 — Auto-Respond MVP (chat idle → decide → continue)

### P1.1 Conversation preferences

- [ ] Migration: `chat_conversations.delegate_auto_respond_*` columns (or JSONB `delegate_prefs`)
- [ ] `PATCH` `/v1/user/conversations/{id}` — extend composer prefs body
- [ ] Persist from Chat UI (checkbox + seconds slider)

### P1.2 Chat UI

- [ ] Composer header: **Auto-Respond** checkbox + delay (sec)
- [ ] Subtitle/tooltip: DE/EN product copy above
- [ ] After `agent.done`: start idle timer; cancel on user typing / send / tab switch policy (document)
- [ ] Badge on synthetic turns: `[Stand-in · auto]` / `[Delegate · auto]` (assistant meta or user message prefix)

### P1.3 Delegate decision call (Variant A — recommended first)

- [ ] `apps/backend/domain/delegate_decision.py`:
  - [ ] Inputs: conversation messages (tail), active `agent_task` goal/requirements, merged delegate config, pending proposals (parsed)
  - [ ] Single LLM call (plain completion, no tools): output **decision brief** + **synthetic user message** text
  - [ ] System prompt: *Act on user goals, not mimic voice; do not ask questions; proceed unless autonomy forbids*
- [ ] Hard rule: if `autonomy.can_*` false for implied action → decision = escalate / stop with reason

### P1.4 Execution

- [ ] **Frontend path (MVP):** timeout → call `POST /v1/user/conversations/{id}/delegate-respond` → returns `{ synthetic_user_message, decision_summary }` → client appends user msg + `runAgentWs()` (same as proposal click)
- [ ] **Backend path (robust, P1.5):** same endpoint triggers server-side `chat_completion` with `agent_unattended` + `agent_permission_ask: false` when workspace + coding agent — works if browser closed

### P1.5 Limits (mandatory)

- [ ] `delegate_max_chain_turns` per conversation (default 3)
- [ ] Reuse `agent_max_tool_rounds` ceiling
- [ ] Wall-clock timeout per delegate chain (e.g. 20 min)
- [ ] Stop triggers: git dirty conflict policy, scan failed, push/merge when `autonomy` denies
- [ ] Daily cap per user (operator setting, mirror `scheduler_max_outbound_per_day` pattern)

### P1.6 Audit

- [ ] `delegate_runs` table + `GET /v1/user/delegate/runs?limit=50`
- [ ] Log: `delegate_run_id`, trigger=`idle`, decision text, `agent_run_id`, outcome
- [ ] Settings page: last 20 runs (read-only)

### P1.7 Tests

- [ ] Unit: decision prompt includes merged delegate, not observations
- [ ] Unit: autonomy deny blocks synthetic “go ahead and merge”
- [ ] Integration: mock LLM → synthetic message → second completion invoked
- [ ] E2E (optional): checkbox persists, timer fires once

---

## Phase P2 — Integration hooks (same delegate brain)

- [ ] **Active task:** inject task `goal` + `requirements` into delegate decision (already partially via `active_task_id`)
- [ ] **Scheduler:** prefix job instructions with merged `workspace_delegate` goals (coding_schedule_execution)
- [ ] **Task runner (future):** `agent_tasks.status = queued` + delegate policy → unattended run (separate epic)
- [ ] Agent prompt tweak: when delegate auto-respond active, suppress `json-proposal` nudge → “decide and execute per delegate goals”

---

## Phase P3 — Observations (passive only)

- [ ] `delegate_observations` table
- [ ] Event hooks (server-side, no LLM):
  - [ ] User message contains test-related ask (heuristic)
  - [ ] User rejected permission / force-push pattern
  - [ ] User accepted delegate synthetic message
- [ ] **No automatic prompt injection**
- [ ] Settings UI: “Observed patterns” read-only panel

---

## Phase P4 — Suggestions (approve to merge)

- [ ] `delegate_suggestions` table + `GET /v1/user/delegate/suggestions`, `POST .../accept`, `POST .../reject`
- [ ] Batch job or post-session analyzer proposes JSON patch to `user_delegate` / `workspace_delegate`
- [ ] UI inbox: *“You asked for tests 17 times — add `prefer_tests: true`?”* Yes / No
- [ ] On accept: merge patch into delegate config (version bump + audit row)
- [ ] Pattern reference: `graph_propose` + apply flow

---

## Phase P5 — Decision examples (retrieval, optional)

- [ ] `delegate_decision_examples` or memory notes tagged `delegate_example`
- [ ] Fields: `situation_summary`, `decision`, `workspace_id?`, embedding for retrieval
- [ ] Inject top-K examples **only** in delegate decision call when similarity > threshold
- [ ] Examples only from **user-confirmed** runs or manual entry — never raw chat mining

---

## Phase P6 — Governance & operator

- [ ] Operator kill-switch: `delegate_enabled` in `operator_settings` (default true for self-hosted)
- [ ] Tenant policy: max auto-respond sec, max chain turns defaults
- [ ] Admin metrics: delegate runs / day, failure rate (no PII in aggregates)

---

## Explicit non-goals (v1)

- [ ] Impersonation: assistant messages forged as human user without `[Stand-in]` marker
- [ ] Silent learning: auto-writing delegate config from chat
- [ ] Unlimited autonomous chains
- [ ] Replacing `user_agent_persona` — keep separate products

---

## File touch list (expected)

| Area | Files |
|------|--------|
| Migrations | `apps/backend/infrastructure/db/migrations/versions/schema_065_*.py` |
| Domain | `delegate_config_schema.py`, `delegate_decision.py`, `delegate_merge.py` |
| Infrastructure | `user_delegate_store.py`, `workspace_delegate_store.py`, `delegate_runs_store.py` |
| API | `apps/backend/infrastructure/user_delegate_api.py`, extend `conversations_api.py` |
| Agent | `apps/backend/domain/agent.py` — optional delegate system block when prefs enabled |
| Frontend | `DelegateSettings.tsx`, Chat composer prefs, `delegate.json` locales |
| Tests | `tests/test_user_delegate_*.py`, `tests/test_delegate_decision.py` |
| Docs | `docs/features/user-delegate.md`, ADR 0007 |

---

## Suggested implementation order (single developer)

1. P0.1 → P0.2 → P0.5 (schema + API + tests)
2. P0.3 (settings UI)
3. P1.1 → P1.3 → P1.4 frontend path → P1.5 → P1.6
4. P1.4 backend path + P2 scheduler prefix
5. P3 → P4 (learning loop with gate)
6. P5 if needed after real usage

---

## Open questions

- [ ] Backend-only auto-respond vs frontend timer first? **Recommendation:** both; frontend for MVP latency, backend worker for reliability.
- [ ] Store delegate prefs on conversation vs user default? **Recommendation:** user default + per-conversation override.
- [ ] Which agents allow delegate execute? **Recommendation:** `coding` + delegated `general`; deny `operator`; `security_auditor` report-only unless workspace delegate enables fix mode.
