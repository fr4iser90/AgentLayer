# AgentLayer × DeepSeek Harness — Integrationsplan

> **Status-Update (Sep 2026):** Dieser Doc behält die **historischen Phasen-Skizzen** (DDD-Greenfield).  
> **Ist-Stand** und Drift-Bewertung: [`dsh-agentlayer-capability-comparison.md`](./dsh-agentlayer-capability-comparison.md).  
> **Goal / Todos / Plan / Round-Driver Workplan:** [`agent-runtime-ux-goal-todos-plan.md`](./agent-runtime-ux-goal-todos-plan.md).  
> Kurz: Compaction + Context-Budget, Session Plan/Todo/Goal, MCP (stdio + HTTP) sind **AL-Style erledigt** — nicht 1:1 wie die Skizzen unten. Externe dsh-Schnittstelle: **won't do**.

## Architektur-Muster

AgentLayer folgt **Domain-Driven Design (DDD) mit Clean Architecture**:

```
api/            ← Transport (FastAPI Router, Auth-Gate)
application/    ← Use Cases, Commands, Queries, DTOs, Ports
domain/         ← Entities, Value Objects, Policies, Protocols (pure, kein IO)
infrastructure/ ← DB, Provider-Clients, externe HTTP, IO-Adapter
```

**Dependency Rule:** `api → application → domain`, `infrastructure` implementiert `domain`-Ports.
Alle neuen Features folgen diesem Pattern — kein direkter Import von `infrastructure` in `api`.

---

## 0. Ausgangslage

| Schicht | AgentLayer (Sep 2026) | dsh |
|---------|------------------------|-----|
| **Inhalt / Tools** | ✅ Python-Tools, Skills, Dashboards, Templates | ✅ TypeScript-Plugins |
| **Auth / Tenant** | ✅ vollständig | ❌ nicht vorhanden |
| **Dashboards** | ✅ vollständig | ❌ nicht vorhanden |
| **Agent-Loop / Session** | ✅ `application/agent_runtime/` | ✅ `session/` |
| **Compaction** | ✅ AL-Style (pre-turn + mid-loop; nicht dsh Surface) | ✅ `compaction-basic/` |
| **Plan-Mode** | ✅ Session soft plan (`plan_mode_*` + Banner) | ✅ `plan/` |
| **Todo-Tracking** | ✅ Session `todo_*` + UI; parallel `agent_tasks` | ✅ `tool-todo/` |
| **Ongoing Goal** | ✅ `goal_*` + Bar + Round-Driver | ✅ `packages/goal/` |
| **Context-Window-Mgmt** | ✅ Budget Soft/Hard + Provider-Usage | ✅ Token-Meter + Compaction |
| **MCP-Client** | ✅ stdio + streamable-http (`mcp_runtime.py`) | ✅ `mcp-client/` |
| **Sandbox** | ⚠️ Docker + Policy; kein Kernel-Jail | ✅ `sandbox/`, `e2b/` |

**Strategie (Stand jetzt):**
- AgentLayer ist **kein Coding-Produkt** (Coding-Agent/Workspace-Tools entfernt). Fokus: Everyday Tools, Dashboards, Knowledge Companion, Multi-Tenant.
- dsh **nicht** als Coding-Ersatz in AgentLayer einbetten.
- Runtime-Ideen aus dsh nur **selektiv in Python adaptieren** — kein TypeScript-Embed. (Großteil der Phasen unten: erledigt AL-Style oder bewusst dünner.)

### Externe Coding-Schnittstelle — **won't do**

Keine dünne Control-Plane in AgentLayer, über die ein externes Coding-Harness (z.B. DeepSeek Harness) angestoßen/orchestriert wird. Coding bleibt außerhalb; AgentLayer bleibt Everyday/Knowledge/Dashboards.

*(Früher: consider / undecided — bewusst verworfen.)*

---

## Phase 1 — Compaction (Höchste Priorität)

**Status:** ✅ **done (AL-Style)** — nicht der Greenfield-Pfad unten. Siehe Comparison Doc Phase 1.  
Ist: `chat_context.py` / `chat_context_loop.py` / `context_budget.py`.

**Was:** Wenn der Kontext zu lang wird, fasst der Agent ältere Teile automatisch zusammen statt zu brechen oder blind zu vergessen.

**Inspiration aus dsh:** `compaction-basic/` — Token-Druck-Messung → Zusammenfassung via LLM → Surface-Replacement

### Historische Skizze (nicht so gebaut)

```
apps/backend/
  domain/agent_runtime/
    compaction.py             ← Plan: CompactionEngine — Ist: in chat_context* verdrahtet
    …
```

**Kernlogik (dsh-Inspiration; AL anders umgesetzt):**
1. Soft/Hard über Context-Budget + Provider-Usage
2. Pre-turn History-Summary + Mid-loop Tool-Round-Drop
3. **Nicht** `<compacted-summary>` Surface-Protocol

**Aufwand (historisch geschätzt):** ~3-4 Tage  
**Lizenz:** MIT — Logik adaptieren ist legal, kein Code-Copy nötig

---

## Phase 2 — Plan-Mode + Todo-Tracking (+ Ongoing Goal)

**Status:** ✅ **done (dünnes Session-Harness)** — nicht DB-PlanSteps + Step-Boundary-Review.  
Ist: `conversation_goal.py`, Tools `goal_*` / `todo_*` / `plan_mode_*`, UI Bar/Panel, Round-Driver.  
Workplan: [`agent-runtime-ux-goal-todos-plan.md`](./agent-runtime-ux-goal-todos-plan.md).

**Was:** Der Agent arbeitet strukturiert, tracked Session-Todos, optional Plan-Mode und Ongoing Goal.

**Inspiration aus dsh:** `plan/plan-mode/`, `todo/tool-todo/`, `packages/goal/`

### Historische Skizze (überdimensioniert; nicht so gebaut)

```
apps/backend/
  domain/agent_runtime/
    plan_mode.py              ← Plan: PlanSteps/Review — Ist: soft PLAN_MODE_GUIDANCE + flag
    todo_list.py              ← Ist: normalize_todos in conversation_goal.py

plugins/tools/platform/conversation_goal/
  session_goal_todos.py       ← Ist: goal_*, todo_*, plan_mode_*
```

**Kernlogik (Ist):**
- Plan-Mode = Session-Flag + Soft-Prompt + `exit_plan_mode` (Markdown-Plan)
- Todos = Session-scoped JSONB, WS-Projection
- Ongoing Goal + Round-Driver für Auto-Continue
- **Kein** Review nach jedem Tool-Call

**Aufwand (historisch):** ~2-3 Tage  
**Abhängigkeit:** Compaction war empfohlen; parallel möglich gewesen

---

## Phase 3 — Context-Window-Management (Token-Meter)

**Status:** ✅ **done (AL-Style)** — Budget + Usage, kein tiktoken-Surface-Meter.  
Ist: `context_budget.py`, Soft 0.8 / Hard 0.95.

**Was:** Token-/Druck-Schätzung des aktuellen Kontexts für Compaction-Trigger und Quotas.

**Inspiration aus dsh:** `llm/token-meter/`

### Historische Skizze (nicht so gebaut)

```
apps/backend/
  infrastructure/agent_runtime/
    context_budget.py         ← Ist: Window/Ratios/Quotas
    # token_meter_tiktoken.py — nicht als dsh-Port nötig
```

**Kernlogik (Ist):**
- Window aus Katalog/Overrides; Soft/Hard-Ratios
- Trigger vor allem über `usage.prompt_tokens` nach LLM-Round
- Kein lokales Surface-Fold

**Aufwand (historisch):** ~1-2 Tage  
**Hinweis:** Alter Plan sagte „zuerst Token-Meter“ — AL hatte Budget schon vor dem Greenfield-Plan.

---

## Phase 4 — MCP-Client (Größte Capability-Erweiterung)

**Status:** ✅ **done (Core)** — stdio + streamable-http in `mcp_runtime.py`; Allowlist live Agents.  
Reconnect/Pool optional offen. Default weiter `AGENT_MCP_ENABLED=false`.

**Was:** Beliebige MCP-Server anbinden → externe Tools ohne Python-Wrapper.

**Inspiration aus dsh:** `mcp/mcp-client/`

### Historische Skizze vs Ist

```
apps/backend/infrastructure/plugins/mcp_runtime.py   ← Ist (nicht separates domain/mcp_*)
# AGENT_MCP_SERVERS_JSON: stdio und/oder transport:streamable-http + url/headers
```

**Was das bringt:**
- Browser-Automation (Playwright MCP)
- Datenbankzugriff (Postgres MCP)
- GitHub-Integration (GitHub MCP)
- Jede MCP-kompatible API sofort nutzbar

**Aufwand (historisch):** ~3-4 Tage  
**Abhängigkeit:** Keine

---

## Phase 5 — Sandbox / Isolation (Optional, später)

**Status:** ⏸️ zurückgestellt (Docker + Tool-Policy reicht).

**Was:** Tool-Ausführung isolieren damit kein Tool den Host beschädigen kann.

**Inspiration aus dsh:** `sandbox/`, `bash-sandbox/`, `fs-sandbox/`

**Entscheidung:** Zurückstellen — Stack läuft Docker-containerisiert. Relevant wenn Multi-Tenant Host-Exec kommt.

---

## Empfohlene Reihenfolge

**Historisch (Plan):** Token-Meter → Compaction → Plan+Todo → MCP → Sandbox.

**Ist (Sep 2026):** Compaction + Budget + Session Goal/Todos/Plan + MCP Allowlist/HTTP erledigt AL-Style. Offen: Compaction-Drifts bei Schmerz, MCP Connection-Pool, Sandbox nur bei Need. Externe dsh-Schnittstelle: won't do.

```
Phase 3 (Token-Meter / Budget)  ← done AL-Style
Phase 1 (Compaction)            ← done AL-Style
Phase 2 (Plan + Todo + Goal)    ← done (Session-Harness)
Phase 4 (MCP-Client)            ← done Core (stdio + HTTP)
Phase 5 (Sandbox)               ← später
```

---

## Lizenz-Check

| Nutzungsform | Erlaubt? |
|---|---|
| dsh-Logik als Inspiration / Portierung in Python | ✅ MIT |
| dsh-TypeScript-Code direkt einbinden | ✅ MIT (mit Notice) |
| dsh als separaten Prozess neben AgentLayer betreiben | ✅ MIT |
| Eigenen Code unter anderer Lizenz veröffentlichen | ✅ kein Copyleft |

Einzige Pflicht: MIT-Copyright-Notice von dsh beibehalten wenn du dsh-Source-Code direkt verwendest.

---

## Referenzen

- [deepseek-ai/deepseek-harness](https://github.com/deepseek-ai/DeepSeek-Harness)
- Lokale Kopie: `/home/fr4iser/Documents/Git/deepseek-harness-master/`
- dsh Compaction-Doku: `packages/compaction/README.md`
- dsh Plan-Doku: `packages/plan/README.md`
- dsh MCP-Doku: `packages/mcp/README.md`
- Aktueller Vergleich: [`dsh-agentlayer-capability-comparison.md`](./dsh-agentlayer-capability-comparison.md)
- Goal/Todos Workplan: [`agent-runtime-ux-goal-todos-plan.md`](./agent-runtime-ux-goal-todos-plan.md)
