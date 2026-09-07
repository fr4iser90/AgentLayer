# AgentLayer ↔ DeepSeek Harness — Capability Comparison (Stand Sep 2026)

**Zweck:** Gegencheck gegen DeepSeek Harness; Status der selektiven AL-Adaptation.  
**Companion:** [`dsh-integration-plan.md`](./dsh-integration-plan.md) (historische Phasen + Status-Update), [`agent-runtime-ux-goal-todos-plan.md`](./agent-runtime-ux-goal-todos-plan.md) (Goal/Todos Workplan).

**Scope:** Token-Meter, Compaction, Plan+Todo+Goal, MCP (+ kurz Sandbox).  
**Strategie:** AgentLayer ist kein Coding-Produkt; dsh-Ideen nur wo Everyday/Knowledge/Agent-Runtime helfen. Externe dsh-Control-Plane: **won't do**.

---

## Snapshot-Matrix

| Phase | dsh | AgentLayer heute | Drift-Schwere |
|-------|-----|------------------|---------------|
| 3 Token-Meter / Context | Eigenes `token-meter` (heuristisch + usage-baseline, Surface-Fold) | Ratio × Provider-Window + `usage.prompt_tokens` | **Mittel** — gleiches Ziel, andere Mechanik |
| 1 Compaction | Surface-Replace + `<compacted-summary>`, pressure + overflow | Pre-turn History-Summary + Mid-loop Tool-Round-Drop als System-Note | **Mittel–Hoch** — vorhanden, aber anderes Modell |
| 2 Plan + Todo + Goal | `plan-mode` + `todo_write` + Ongoing Goal / round-driver | Conversation goal/todos: `plan_mode_*`, `todo_*`, `goal_*`, Round-Driver, Chat-UI; parallel `agent_tasks` | **Niedrig** — AL-Style done (nicht dsh-1:1) |
| 4 MCP-Client | stdio + streamable-http, reconnect, persistente Tools | stdio + `streamable-http`; connect-per-call; Allowlist auf live Agents | **Niedrig–Mittel** — Transport da; Lifecycle ephemeral |
| 5 Sandbox | Kernel FS-Confine (bwrap/Landlock/…) | `AGENT_MODE=sandbox` = Policy „container“, Docker außen | **Hoch** vs dsh; **OK** für aktuellen Scope |

---

## Phase 3 — Token-Meter / Context-Window

### dsh (`packages/llm/token-meter/`)

- Service `ctx.tokenMeter.measure(session)` → Snapshot mit `totalTokens`, Surface-Nodes, Baseline.
- Heuristik ~4 chars/token + Overheads; Baseline aus Provider-Usage wenn Envelope matcht.
- Surface-Fold: Append/Replace (inkl. Compaction) aktualisiert Deltas live (auch negativ nach Shrink).
- Soft/Hard **nicht** im Meter: Soft ≈ Compaction `thresholdRatio` × `contextWindow`; Hard ≈ `CONTEXT_WINDOW_EXCEEDED`.
- Optional UI-Projections: pressure / projected / breakdown.

### AgentLayer

- `infrastructure/agent_runtime/context_budget.py` — Window aus Katalog/Override; Soft **0.8**, Hard **0.95**.
- Trigger über `usage.prompt_tokens` nach LLM-Round (`should_compact_by_usage`).
- Quotas (Tool-Schema, Message/Tool-Result/Compaction-Chars) aus denselben Ratios (`CHARS_PER_TOKEN_ESTIMATE = 4`).
- Kein lokales Surface-Fold; kein Slice-Breakdown (system/tools/history/buffer).
- Ohne bekanntes Window: Budgeting/Soft-Trigger weitgehend aus.

### Drifts

| Thema | dsh | AgentLayer | Bewertung |
|-------|-----|------------|-----------|
| Messung vor dem Call | Surface-Heuristik (± usage baseline) | Vor allem **nach** dem Call via Provider-Usage | AL reaktiv; dsh kann pressure **vor** Step schätzen |
| Persistente Token-Fold | Ja (Session-Surface) | Nein | AL muss auf Provider zählen |
| Capacity | Adapter `contextWindow` | Katalog / Overrides / optional Default | Ähnlich |
| Soft/Hard | Compaction-Config + overflow error | Explizite Soft/Hard-Ratios | AL klarer getrennt |
| Breakdown für UI | Optional projections | Runtime-API Snapshot, kein dsh-Style Breakdown | Nice-to-have |

### Empfehlung

- **Nicht** tiktoken-Meter 1:1 portieren, solange Provider-Usage zuverlässig ist.
- Optional: leichter Pre-Flight-Estimate (4 chars/token) nur für UI/Warnung — kein Blocker.
- Plan-Doc Phase „Token-Meter zuerst“ ist für AL **falsch priorisiert**: Budget existiert schon.

---

## Phase 1 — Compaction

### dsh (`packages/compaction/compaction-basic/`)

- Triggers: `agent/pre-step` (pressure), `CONTEXT_WINDOW_EXCEEDED` (overflow), `/compact` (manual).
- Range: Tail `retainRatio` (default **0.16**) oder `retainTokens`; Head wird summarisiert.
- Transaction: Surface-`replace` → User-Message mit `<compacted-summary>…</compacted-summary>`.
- Shrink-Regel: Summary muss kürzer sein; Retries `compactionRetries` / `maxOverflowRetries`.
- Optional Tool-Result-Pruner vor Compact.

### AgentLayer

- **Pre-turn** (`chat_context.py` / `prepare_chat_history_for_llm`): ältere History → LLM-Summary in DB (`context_summary`) + System-Message; letzte N Messages verbatim (`RECENT_VERBATIM_MESSAGES`, default 12).
- **Mid-loop** (`chat_context_loop.py`): bei Soft/Hard älteste Tool-Rounds droppen, in `agent_loop_context_summary` falten, als System-Note wieder einfügen; Char-Caps immer.
- Knobs: `CHAT_CONTEXT_COMPACTION_*`, `context.compaction_enabled`, Keep-Recent-Tool-Rounds, Soft/Hard aus Budget.
- Kein Surface-Replace-Tag; kein Overflow-Retry-Loop wie dsh; Mid-loop re-metert nicht lokal nach Drop.

### Drifts

| Thema | dsh | AgentLayer | Bewertung |
|-------|-----|------------|-----------|
| Wann | Pre-step + overflow + manual | Pre-turn + mid tool-loop | Beide decken Pressure ab; AL stärker auf Chat-History/DB |
| Was bleibt | Token-Tail (Ratio des Windows) | Message-Count / Tool-Round-Count | Unterschiedliches Retain-Modell |
| Wie ersetzt | Surface replace + tagged summary | System-Note + persisted summary | Semantik anders; Tools/KV-Cache-Story dsh-spezifisch |
| Overflow-Recovery | Dedizierter Path + Retries | Hard → aggressiver Trim; kein dsh-Overflow-Compact | AL dünner bei echten Context-Errors |
| Architektur | Eigenes Compaction-Plugin | In `chat_context*` verdrahtet | Plan-Skizze (DDD CompactionEngine) ≠ Ist-Zustand |

### Empfehlung

- Compaction als **done (AL-Style)** behandeln, nicht greenfield „Phase 1 bauen“.
- Sinnvolle Drifts schließen nur bei Schmerz: Overflow-Retry, manuelles `/compact`, Retain an Window-Tokens statt fester Message-Counts.
- **Nicht** `<compacted-summary>` Surface-Protocol übernehmen, solange kein dsh-Surface-Log existiert.

---

## Phase 2 — Plan-Mode + Todo + Ongoing Goal

### dsh

- **Plan-Mode:** Soft Guidance (`plan:policy` System-Section); State `plan/mode` im Log; `/plan`, `exit_plan_mode` + User-Approve; ändert Sandbox/Approvals **nicht**.
- **Todo:** `todo_write` ganze Liste ersetzen; Status `pending|in_progress|completed`; Projection bis `turn/start`; unabhängig von Plan-Mode.
- **Ongoing Goal:** Goal-Tools + UI-Bar; optional Round-Driver für autonome Continuation.

### AgentLayer (done, AL-Style — Sep 2026)

- **Conversation goal & todos** (conversation-scoped, nicht `agent_tasks`):
  - Domain: `domain/agent_runtime/conversation_goal.py`
  - Store: `session_goal` / `session_todos` / `session_plan_mode` (Migrations `schema_116`, `schema_117`)
  - Tools: `goal_*`, `todo_*`, `plan_mode_set`, `exit_plan_mode` (`plugins/tools/platform/conversation_goal/`)
  - WS: `agent.goal`, `agent.todos`, `agent.plan_mode`, `agent.goal_round`
  - Round-Driver: `goal_round_driver.maybe_emit_goal_round` → UI Auto-Continue
  - UI: Ongoing Goal Bar, Todos Panel, Plan-Mode Banner
- **Produkt-Tasks** bleiben getrennt: `agent_tasks` + Tasks-Dashboard = persistenter Backlog.
- Coding/`coding_plan`-Plan-Mode: entfernt; Session-Plan-Mode ist soft prompt + Tools, kein Sandbox-Switch.
- Kein dsh Step-Boundary-Review nach jedem Tool (bewusst dünner).

### Drifts

| Thema | dsh | AgentLayer | Bewertung |
|-------|-----|------------|-----------|
| Collaboration „denk zuerst“ | Plan-Mode | Soft prompt + `plan_mode_*` + Banner | **Done** (leichter als dsh Approve-Flow) |
| Kurzlebige Todos | Session-Tool | `todo_write` / `todo_read` + UI | **Done** |
| Ongoing Goal + Autonomie | Goal + Round-Driver | Goal tools + Bar + `agent.goal_round` | **Done** |
| Persistente Arbeit | — | `agent_tasks` | AL behält Produkt-Backlog |

### Empfehlung

- Feature als **done** behandeln; Polish nur bei UX-Schmerz (Prompt-Hinweis für Agents noch optional).
- Alter Integrationsplan Phase 2 (DB PlanSteps + Review nach jedem Tool) bleibt **overkill** — nicht nachbauen.

---

## Phase 4 — MCP-Client

### dsh (`packages/mcp/mcp-client/`)

- Transports: **stdio** + **streamable-http**.
- Persistente Connection, reconnect (backoff), Tools als normale `ctx.tools`.
- Namen `mcp__<server>__<tool>`; Wire-Name raw; Timeout/Fail-on-startup konfigurierbar.

### AgentLayer (`infrastructure/plugins/mcp_runtime.py`)

- Transports: **stdio** + **streamable-http** (`transport`, `url`, `headers` in `AGENT_MCP_SERVERS_JSON`).
- Discovery + Invoke; Prefixe `mcp__…`.
- Config: `AGENT_MCP_*`, Workspace `mcp_stdio_servers` ersetzt Global.
- Connect oft **pro Call** (frisch spawnen / HTTP session), nicht langlebiger Client wie dsh.
- Default `AGENT_MCP_AGENT_IDS` auf **live Agents** (nicht mehr `coding*`).
- Default `AGENT_MCP_ENABLED=false`.

### Drifts

| Thema | dsh | AgentLayer | Bewertung |
|-------|-----|------------|-----------|
| HTTP MCP | Ja | Ja (`streamable-http`) | **Done** (Config); live-Ops noch dünn getestet |
| Lifecycle | Reconnect + stable registry | Ephemeral spawn | Ops/Latenz-Drift bleibt |
| Agent-Wiring | Plugin immer an Tools | Allowlist + Flag | **Fixed** (Defaults live) |
| Capability-Explosion | Hoch | Gleich möglich sobald enabled | Feature-Flag, kein Gap |

### Empfehlung

1. ~~Allowlist fixen~~ — done.
2. ~~HTTP-Transport~~ — done (Config-Pfad).
3. Optional: Connection-Pool/Reconnect — Qualitätsdrift, kein Must.

---

## Phase 5 — Sandbox (kurz)

| | dsh | AgentLayer |
|--|-----|------------|
| Bedeutung | Process-Confine für FS-Effekte (bwrap/…) | `AGENT_MODE=sandbox` → Tools als `container`-Policy; Host-Tools geblockt |
| Coding-Shell-Jail | Ja (bash/fs-sandbox) | Coding-Tools entfernt; irrelevant für Core |
| Empfehlung | Nicht portieren | Docker + Policy reicht; erst bei Multi-Tenant Host-Exec neu bewerten |

---

## Was der alte `dsh-integration-plan.md` falsch priorisiert hatte

1. Markierte Compaction / Context / MCP als ❌ — **waren schon (teilweise) da**; Plan hat Status-Update (Sep 2026).
2. Reihenfolge „Token-Meter → Compaction“ — **AL hatte beides schon**, Meter anders.
3. Phase-2-Skizze (PlanSteps + Review) war **dicker** als dsh — AL baute dünnes Session-Harness statt dessen.
4. Externe Coding-Schnittstelle: **won't do** (nicht in Runtime-Phasen).

---

## Vorgeschlagene Reihenfolge (AL-realistisch) — Status

**Workplan:** [`agent-runtime-ux-goal-todos-plan.md`](./agent-runtime-ux-goal-todos-plan.md)

```
A. MCP Allowlist fixen (Defaults weg von coding*)     ← done (P0)
B. Vision-Attach disable ohne VLM                     ← done (P0)
C. Session Todos + Ongoing Goal (+ Chat-UI)           ← done (P1/P2)
D. Activity-Stream polish (Think / Tool-Labels)       ← done (P2)
E. Compaction-Drifts nur bei Schmerz                  ← später / optional
F. MCP HTTP / Plan-Mode / Round-Driver                ← done (P3)
G. Externe dsh-Schnittstelle                          ← won't do
```

**Vision-Button:** Chat-Image-Attach („+“). Kein dsh-Konzept. Disabled ohne VLM.

**Ongoing Goal:** Goal-Tools + UI-Projection; Prompt steuert Tool-Nutzung; Round-Driver emittiert `agent.goal_round`.

**Nicht empfehlen:** Greenfield-Port von token-meter + compaction-basic „wie dsh“.

---

## Referenzen

- dsh: `/home/fr4iser/Documents/Git/deepseek-harness-master/`
  - Token: `packages/llm/token-meter/`, `docs/subsystems/token-meter.md`
  - Compaction: `packages/compaction/compaction-basic/`, `docs/subsystems/compaction.md`
  - Plan/Todo: `packages/plan/plan-mode/`, `packages/todo/tool-todo/`
  - Goal / Ongoing Goal: `packages/goal/` (`tool-goal`, `goal-round-driver`)
  - MCP: `packages/mcp/mcp-client/`
  - Sandbox: `packages/sandbox/`, `docs/subsystems/sandbox.md`
- AgentLayer:
  - Budget: `apps/backend/infrastructure/agent_runtime/context_budget.py`
  - Compaction: `chat_context.py`, `chat_context_loop.py`, `chat_turn_preparation.py`
  - Conversation goal: `domain/agent_runtime/conversation_goal.py`, `conversation_goal_store.py`, `plugins/tools/platform/conversation_goal/`
  - Goal round: `application/.../goal_round_driver.py`
  - MCP: `apps/backend/infrastructure/plugins/mcp_runtime.py` (stdio + streamable-http)
  - Mode: `operator_settings_readers.resolved_agent_mode`, `tool_policy.effective_execution_context`
  - Activity-UI: `apps/frontend/src/features/chat/AgentActivityPanel.tsx`, `ConversationGoalPanels.tsx`
- Workplan UX: `docs/planning/agent-runtime-ux-goal-todos-plan.md`
- Integrationsplan (historisch + Status): `docs/planning/dsh-integration-plan.md`
