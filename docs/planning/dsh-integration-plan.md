# AgentLayer × DeepSeek Harness — Integrationsplan

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

| Schicht | AgentLayer | dsh |
|---------|-----------|-----|
| **Inhalt / Tools** | ✅ Python-Tools, Skills, Dashboards, Templates | ✅ TypeScript-Plugins |
| **Auth / Tenant** | ✅ vollständig | ❌ nicht vorhanden |
| **Dashboards** | ✅ vollständig | ❌ nicht vorhanden |
| **Agent-Loop / Session** | ✅ `application/agent_runtime/` | ✅ `session/` |
| **Compaction** | ❌ fehlt | ✅ `compaction-basic/` |
| **Plan-Mode** | ❌ fehlt | ✅ `plan/` |
| **Todo-Tracking** | ❌ fehlt | ✅ `tool-todo/` |
| **Context-Window-Mgmt** | ❌ fehlt | ✅ Token-Meter + Compaction |
| **MCP-Client** | ❌ fehlt | ✅ `mcp-client/` |
| **Sandbox** | ❌ fehlt | ✅ `sandbox/`, `e2b/` |

**Strategie:** dsh **nicht ersetzen** — selektiv die fehlenden Runtime-Teile aus dsh **adaptieren** (in Python), weil dein Stack Python/FastAPI ist und dsh TypeScript. Direktes Einbetten von dsh-Packages wäre ein Technologie-Bruch.

---

## Phase 1 — Compaction (Höchste Priorität)

**Was:** Wenn der Kontext zu lang wird, fasst der Agent ältere Teile automatisch zusammen statt zu brechen oder blind zu vergessen.

**Inspiration aus dsh:** `compaction-basic/` — Token-Druck-Messung → Zusammenfassung via LLM → Surface-Replacement

### Umsetzung in AgentLayer (DDD-konform)

```
apps/backend/
  domain/agent_runtime/
    compaction.py             ← CompactionEngine (abstrakt, pure), CompactionPolicy
    compaction_policy.py      ← ThresholdRatio, RetainRatio, Config (Value Objects)
    value_objects.py          ← CompactionResult, CompactionRange (ergänzen)

  application/agent_runtime/
    ports.py                  ← CompactionSummarizer Protocol (ergänzen)
    use_cases/
      compact_session.py      ← CompactIfNeeded, CompactNow (orchestriert domain + infra)

  infrastructure/agent_runtime/
    compaction_basic.py       ← LLM-Summarizer (konkreter IO-Adapter)
    token_meter_tiktoken.py   ← Token-Zählen via tiktoken (konkreter Adapter)
```

**Kernlogik (aus dsh portiert):**
1. Nach jedem Step: Tokens messen (`tokenMeter`)
2. Über Schwellenwert (default 80% des Context-Window)? → compact
3. Älteste Surface-Einträge nehmen, Tail behalten (default 16%)
4. LLM-Call zur Zusammenfassung → `<compacted-summary>` Tag
5. Original-Messages durch Summary ersetzen in Session

**Aufwand:** ~3-4 Tage
**Lizenz:** MIT — Logik adaptieren ist legal, kein Code-Copy nötig

---

## Phase 2 — Plan-Mode + Todo-Tracking

**Was:** Der Agent arbeitet strukturiert Pläne ab, tracked Todos in der Session, zeigt Fortschritt.

**Inspiration aus dsh:** `plan/plan-mode/`, `todo/tool-todo/`

### Umsetzung in AgentLayer (DDD-konform)

```
apps/backend/
  domain/agent_runtime/
    plan_mode.py              ← PlanModeState, PlanStep, StepStatus (Entities/VOs, pure)
    todo_list.py              ← TodoItem, TodoList (Entities, pure)

  application/agent_runtime/
    use_cases/
      plan_execution.py       ← StepTransition, ReviewFlow (orchestriert domain + infra)
    dtos/
      plan_dtos.py            ← PlanCreateRequest, PlanStepDTO

  infrastructure/agent_runtime/
    plan_persistence.py       ← DB-Adapter für Plan/Todo-State

plugins/tools/platform/
  plan/plan.py                ← Tool: plan_create, plan_update, plan_complete
  todo/todo.py                ← Tool: todo_write, todo_read
```

**Kernlogik:**
- Plan-Mode ist **separater Zustand** pro Session (nicht generischer Mode-Switch)
- Todos sind **Session-scoped**, persistent in der DB
- Step-Boundary: nach jedem Tool-Call prüfen ob Step abgeschlossen
- Review-Flow: Plan-Step → Agent-Bestätigung → nächster Step

**Aufwand:** ~2-3 Tage
**Abhängigkeit:** Phase 1 (Compaction) empfohlen vorher

---

## Phase 3 — Context-Window-Management (Token-Meter)

**Was:** Genaue Token-Messung des aktuellen Kontexts (System-Prompt + Tools + History + Buffer).

**Inspiration aus dsh:** `llm/token-meter/`

### Umsetzung in AgentLayer (DDD-konform)

```
apps/backend/
  domain/agent_runtime/
    token_meter.py            ← TokenMeter Protocol, ContextBudget (VO, pure)

  application/agent_runtime/
    ports.py                  ← TokenMeterPort Protocol (ergänzen)

  infrastructure/agent_runtime/
    token_meter_tiktoken.py   ← tiktoken-basierter Adapter (OpenAI/DeepSeek)
    token_meter_anthropic.py  ← Anthropic Token-Adapter (optional)
```

**Kernlogik:**
- Messe nach jedem Step: System-Prompt + Tools-Schema + History + aktueller Buffer
- Liefert: `{ total, system, tools, history, buffer, capacity, pressure_ratio }`
- Wird von Compaction (Phase 1) konsumiert

**Aufwand:** ~1-2 Tage
**Abhängigkeit:** Wird für Phase 1 gebraucht — sollte zuerst gebaut werden

---

## Phase 4 — MCP-Client (Größte Capability-Erweiterung)

**Was:** Beliebige MCP-Server anbinden → sofort hunderte externer Tools nutzbar ohne Python-Wrapper.

**Inspiration aus dsh:** `mcp/mcp-client/`

### Umsetzung in AgentLayer (DDD-konform)

```
apps/backend/
  domain/tools/
    mcp_server.py             ← McpServer Entity, McpToolDefinition (pure)

  application/tools/
    use_cases/
      mcp_tool_discovery.py   ← Tool-Discovery + Registration Use Case
    ports.py                  ← McpClientPort Protocol

  infrastructure/mcp/
    mcp_client.py             ← MCP-Protokoll-Client stdio/SSE (IO-Adapter)
    mcp_registry.py           ← Server-Registry (DB/Config-Adapter)

plugins/tools/integrations/
  mcp/mcp_bridge.py           ← MCP-Tools als AgentLayer-Tools exposen

content/mcp-servers/
  servers.yaml                ← Konfigurierte MCP-Server je Tenant
```

**Was das bringt:**
- Browser-Automation (Playwright MCP)
- Datenbankzugriff (Postgres MCP)
- GitHub-Integration (GitHub MCP)
- Jede MCP-kompatible API sofort nutzbar

**Aufwand:** ~3-4 Tage
**Abhängigkeit:** Keine — kann parallel zu Phase 1-3 gebaut werden

---

## Phase 5 — Sandbox / Isolation (Optional, später)

**Was:** Tool-Ausführung isolieren damit kein Tool den Host beschädigen kann.

**Inspiration aus dsh:** `sandbox/`, `bash-sandbox/`, `fs-sandbox/`

**Entscheidung:** Erstmal zurückstellen — dein Stack läuft Docker-containerisiert, das ist bereits eine Isolation-Schicht. Relevant wenn Multi-Tenant-Code-Ausführung kommt.

---

## Empfohlene Reihenfolge

```
Phase 3 (Token-Meter)     ← 1-2 Tage  — Fundament für Compaction
    ↓
Phase 1 (Compaction)      ← 3-4 Tage  — Größter Impact auf Qualität
    ↓
Phase 2 (Plan + Todo)     ← 2-3 Tage  — Strukturiertes Arbeiten
    ↓
Phase 4 (MCP-Client)      ← 3-4 Tage  — Capability-Explosion
    ↓
Phase 5 (Sandbox)         ← später    — Nice to have
```

**Gesamtaufwand:** ~10-13 Tage für Phasen 1-4

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
