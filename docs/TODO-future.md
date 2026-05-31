# Future work (tracked goals)

English-only backlog for product and research ideas—not a commitment order.

---

## Chat feedback (UX)

- [x] Add explicit **feedback controls** in chat UI: **thumbs up / thumbs down** (or equivalent) so users can mark responses as helpful or not. **Done:** `MessageFeedbackButtons` on assistant turns; `PUT /v1/user/conversations/{id}/feedback`.
- [x] Persist feedback with **message/thread identifiers** and optional short comment (later). **Done:** `chat_message_feedback` table (`conversation_id` + `message_position`); optional `comment` field on API.
- [x] Expose feedback in **admin/analytics** for quality review (privacy/access rules TBD). **Done (MVP):** `GET /v1/admin/message-feedback` (tenant-scoped, admin-only).

---

## Optional “monitor layer” (observability)

- [ ] Add a **toggleable monitor layer** (opt-in) that records structured traces for debugging and improvement loops. **Foundation (chat path):** `agent_run_id` per `chat_completion`, persisted `agent_runs` + `tool_invocations`, admin **`GET /v1/admin/run-traces`** + UI `/app/admin/run-traces` — not yet operator-toggleable or stack-selectable.
- [ ] Let operators choose **which stack is monitored** (non-exclusive list; each may have limits):
  - **IDE Agent** (Playwright/CDP path, tool actions tied to IDE).
  - **External** API models (hosted LLMs).
  - **Catalog providers** (``provider_1``, ``provider_2``, local OpenAI-compatible stacks)—note: hook depth varies by integration; treat as best-effort or out-of-scope for v1.
- [ ] For supported paths, capture at minimum: **prompts** (user + system where applicable), **tool calls / tool results**, **model identifiers**, **timestamps**, **session/thread id**, **errors**. **Partial (chat):** tool name/args/excerpt, model id, timestamps, `agent_run_id`, errors in logs + run-traces; **prompts not stored** in queryable store yet.

---

## Goals, outcomes, and follow-up analysis

- [ ] Define a lightweight **goal / outcome** model (e.g. task completed, user satisfied, escalation)—even if heuristic at first.
- [ ] Support **multi-turn context**: attach **follow-up prompts** so analysis can tell whether the user **retried**, **changed approach**, or **abandoned** a line of inquiry.
- [ ] Use aggregated traces + feedback to:
  - refine **routing/heuristic triggers** (when to suggest tools, when to hand off, etc.);
  - detect **systematic failure modes** (repeated thumbs-down on same flows).

---

## Data pipeline (collect → analyze → improve)

- [ ] **Store** monitor + feedback data in a queryable store (respect retention, PII, and admin-only access). **Partial:** `agent_runs` + `tool_invocations` (admin run-traces); no feedback table; no prompt retention policy.
- [ ] **Offline or batch analysis** jobs: clustering, simple dashboards, export for human review.
- [ ] **Close the loop**: translate insights into **config/code changes** (prompt tweaks, tool policies, IDE selector maintenance)—with versioning and rollback.

---

## Coding agent roadmap (prioritized backlog)

Source detail: `docs/planning/coding-agent-roadmap.md` (phases G/H, checklist, epics A–E).  
Order below is **recommended implementation priority** (security and correctness first, then user-visible “done” signals, then depth).

### P0 — Security and workspace correctness

- [ ] **Epic A — Workspace authorization (server-side):** Extend checks beyond DB row match where product adds sharing (e.g. `share_permissions`, multi-member rows). **Done (this slice):** chat `chat_completion` **fail-closed** when the client sends `workspace_id` but `ensure_workspace` did not resolve a tree (`_raise_if_workspace_inaccessible` in `apps/backend/domain/agent.py`); **`coding_plan`** always requires a resolved workspace.
- [ ] **Regression tests:** HTTP / WS integration tests for foreign `workspace_id` (optional). **Done (unit):** `tests/test_workspace_chat_gate.py` for `_raise_if_workspace_inaccessible`.

### P1 — Verify-in-the-loop (Phase 4 completion)

- [x] **Auto-inject verify recap:** After a batch that ran `workspace_verify`, a **`[Workspace verify recap]`** system line is appended (output capped) so the next LLM round sees the result without manual copy-paste.
- [x] **Dedicated tool:** `workspace_verify` runs **only** `verify_command` from `{workspace}/.agentlayer.json` (same dangerous-pattern blocklist as `bash`; timeout `AGENT_WORKSPACE_VERIFY_TIMEOUT_SEC`). Bad `workspace_id` on chat → HTTP **403** via `WorkspaceAccessDenied`.
- [ ] **Opt-in default:** Start with explicit tool calls (current); document in `docs/features/coding-workflow.md` when auto-run is added.

### P2 — Search / index / LSP (Phase 3 completion)

- [ ] **Index-on-attach (operator flag):** Optional background index when a workspace is selected or opened; cap CPU/time; surface progress in UI or logs. **Done:** `maybe_schedule_index_on_attach`; operator toggle `workspace_index_on_attach_enabled` (Admin → Interfaces → Platform) or env `AGENT_WORKSPACE_INDEX_ON_ATTACH`. **Open:** attach progress in UI.
- [x] **Ripgrep or fast path:** Literal ``search`` uses **ripgrep** when ``rg`` is on ``PATH`` (or ``AGENT_RIPGREP_PATH``); timeout ``AGENT_RIPGREP_TIMEOUT_SEC``; falls back to Python walk. Regex mode stays Python. Response includes ``search_engine``.
- [ ] **LSP runbook:** Per-language smoke (Python/TS minimum), compose PATH notes, and clearer surfacing of diagnostics inside tool JSON for the model.

**Retrieval / incremental index (3-stage plan):** Full spec + file-level change list → [`docs/planning/retrieval-incremental-index-roadmap.md`](planning/retrieval-incremental-index-roadmap.md).

- [x] **Stufe A (P2 priority):** Post-write incremental index (debounced, touched files only) → Qdrant + Neo4j `upsert_file_graph`; hooks on `write_file` / `edit` / `replace` / `apply_patch`; env `AGENT_WORKSPACE_INDEX_ON_WRITE`.
- [x] **Stufe B:** Operator/workspace policy (`index_on_write`, graph toggle), per-file stale (`workspace_index_file_state`), graph in RRF when requested; UI in WorkspaceRetrievalBar + Admin Interfaces.
- [x] **Stufe C:** Reindex after `git pull` (operator flag); nightly stale reindex scheduler; `POST /v1/admin/workspaces/{id}/reindex`.

### P3 — Subagents and observability (Phase 5 + Phase 1 tail)

- [x] **Cancellation + accounting:** Parent **WebSocket cancel** is observed **between tool calls** in the planner loop (`before_tool`); plan subagent receives the same ``cancel_event`` and optional ``agent_parent_run_id`` for log correlation. (Token/cost accounting still open.)
- [x] **Milestone H2 — UI:** Dedicated “plan subagent result” surface (summary + link to internal run id / log id when available), not only raw tool JSON. **Done (slice):** subagent run cards + **run id link** to `/app/admin/run-traces?run=…`; subtitle from subagent_done text.
- [x] **Trace id per chat run:** Each `chat_completion` assigns **`agent_run_id`** (UUID); logged at start; included on **`agent.session`**, **`agent.llm_round_start`**, **`agent.llm_round`**, **`agent.tool_start`**, **`agent.tool_done`**, **`agent.done`**, cancel/step_wait events; top-level **`agent_run_id`** on the JSON response body. Admin: **`GET /v1/admin/run-traces`**, UI `/app/admin/run-traces`.

### P4 — Plan vs build polish (Phase 2)

- [ ] **Auto-routing (optional):** First *N* tool rounds or first user turn with `coding_plan`, then hand off to `coding` with an explicit system handoff line (configurable; off by default).

### P5 — Product epics (larger than single PRs)

- [ ] **Epic B — Git:** Read-only (status, log, diff, branch) → local commit rules → network fetch/push with credentials, egress, audit. **Done (slices):** `git_read` (read-only); `git_sync` / `git_push` (network, credential-aware). **Open:** local commit tool/rules, egress limits, audit trail, epic closure.
- [ ] **Epic C — Tasks / follow-ups:** Lightweight tasks or deep links from thread to “open work” (UI + JSON first).
- [ ] **Epic E — Testing in the loop:** One canonical verify command per repo kind; optional CI webhook; align with P1 once verify runs exist. **Partial:** per-workspace `verify_command` in `.agentlayer.json` + `workspace_verify` tool (P1); no CI webhook.
- [ ] **Epic D — Background planner:** Defer until A + B read path feel solid; explicit “suggest plans” single round-trip as smaller step.

### P6 — Checklist niceties (agentic parity)

- [ ] **Patch-first defaults:** Prompt nudge + optional metrics: patch vs full write vs replace.
- [ ] **Budgets:** Per-agent `max_tool_rounds` override in UI/API; warn when remaining rounds are low. **Done (backend slice):** chat body `agent_max_tool_rounds`, env `AGENT_MAX_TOOL_ROUNDS`, near-limit system reminder in planner loop. **Open:** per-agent UI override (scheduler has operator `scheduler_max_tool_rounds` only).
- [ ] **Session working memory (semantic):** Compressed narrative summary of the session (LLM or heuristic truncator), separate from tool-name recap.
- [ ] **Tool-JSON helper model (optional):** Second small model or repair pass for malformed tool calls—only if metrics show need.

### Hygiene (ongoing)

- [ ] **Single narrative:** Keep `docs/features/coding-workflow.md`, `coding-agent-roadmap.md`, and `compose.yaml` comments aligned on “where coding runs” and persistence expectations. **Partial:** ADR 0005 + runbook + compose named volume documented; periodic re-audit still useful.
- [ ] **Epic F smoke (ops):** After deploy, workspace create → file write → `docker compose restart` → file still present (see runbook `docs/runbooks/workspace-persistence.md`). **Done (infra + runbook):** compose volume `agent_project_workspaces`, runbook steps documented. **Open:** recurring post-deploy smoke checklist.

---

## User Delegate (Stellvertreter)

Delegated **decision authority** (not chat persona): global `user_delegate`, per-workspace overlay, Auto-Respond after idle timeout, audit + hard caps. Learning only via observe → suggest → user confirms.

- **ADR:** [`docs/adr/0007-user-delegate.md`](adr/0007-user-delegate.md)
- **Full checklist:** [`docs/planning/user-delegate-roadmap.md`](planning/user-delegate-roadmap.md)

### Priority snapshot

- [x] **P0:** Schema + `/v1/user/delegate` + workspace delegate API + Settings UI (Stellvertreter)
- [x] **P1 (MVP slice):** Chat Auto-Respond checkbox + idle sec (`PATCH …/delegate-prefs`); idle timer → `POST …/delegate-respond` → synthetic user message + `[Stand-in · auto]` badge; `delegate_runs` audit + `GET /v1/user/delegate/runs`. **Open:** backend unattended path, settings run history UI, full chain limits polish.
- [ ] **P2:** Reuse delegate merge in scheduler jobs + active task context
- [ ] **P3–P5:** Observations, suggestion inbox, optional decision-example retrieval

---

## Notes

- Local catalog provider monitoring may remain **limited** until a clear hook surface exists; document constraints when implementing.
- All monitoring should stay **opt-in** and **documented** for operators and end-users where required.
