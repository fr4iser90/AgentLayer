# Agent Runtime UX — Goal, Todos, Activity (Workplan)

**Stand:** Sep 2026 (Coding-Merge nachgezogen)  
**Bezug:** Screenshot dsh (Think / Bash / Write / To-dos / **Ongoing Goal**), Vergleich `dsh-agentlayer-capability-comparison.md`  
**Ziel:** gleiche *Arbeitsklarheit* für Everyday / Knowledge / Coding / lange Agent-Läufe.

**Update 2026-09-07:** Der Coding-Vertical ist zurück (siehe `coding-agent-roadmap.md`) und teilt jetzt **dieselbe**
Harness. Das alte prozess-globale `todo`-Tool (`plugins/tools/workspace/planning/todo.py`) ist gelöscht — es war
für alle User und Conversations derselbe In-Memory-Array und tauchte in keiner UI auf. `coding` / `coding_plan`
haben die vollen 7 Harness-Tools, `security_auditor` Goal + Todos (kein Plan-Mode: der Auditor liefert Findings).

---

## Kurz: Was ist was?

| Begriff | Was es ist | Was es **nicht** ist |
|---------|------------|----------------------|
| **Vision-Button** | Chat „+“ / Image-Attach | Ein dsh-Feature. Bei uns: Upload von Bildern für VLM. Soll **disabled** sein, wenn kein VLM-Modell konfiguriert (`model_vlm` / Profil `vlm` leer). |
| **Ongoing Goal** (dsh) | Session-State + Tools `create_goal` / `get_goal` / `update_goal` + UI-Bar (Pause/Edit/Delete). Driver kann Rounds autonom weitertreiben. | **Nicht** der System-Prompt. Der Prompt sagt dem Modell nur *wann/wie* Goal-Tools zu nutzen; die Bar zeigt den **gefalteten Goal-State**. |
| **To-dos** (dsh) | Session-Tool `todo_write` (ganze Liste ersetzen) → Projection in der Activity-UI | Nicht dasselbe wie Produkt-`agent_tasks` (persistenter Backlog) |
| **Plan-Mode** (dsh) | Soft „denk/plane zuerst“ + `exit_plan_mode` | Optional; weniger kritisch als Goal+Todos für die UX im Screenshot |
| **Activity-Stream** | Think / Tool-Zeilen mit Labels | Bei uns: `AgentActivityPanel` + WS `agent.tool_*` / `agent.llm_*` — roh vorhanden, Optik/Lesbarkeit ≠ dsh |

---

## Bewertung: Was funktioniert besser?

### dsh gewinnt klar bei

1. **Langläufer-Klarheit** — Ongoing Goal + Todos halten Mensch und Modell auf derselben Agenda.
2. **Activity-Lesbarkeit** — Think / Bash / Write als typisierte Zeilen, nicht generisches JSON.
3. **Autonomie mit Kontrolle** — Pause/Edit/Delete am Goal; Modell markiert complete/blocked.

### AgentLayer gewinnt / reicht bei

1. **Context budget + Compaction** — Soft/Hard + Pre-turn/Mid-loop schon produktiv (anders als dsh, aber da).
2. **Produkt-Tasks** (`agent_tasks`) — echte persistente Arbeit über Sessions/Dashboards; dsh-Todos sind ephemeral.
3. **Multi-Tenant / Agents / Tools** — anderes Produkt; Coding-Harness-UX 1:1 kopieren wäre falsch.

### Hybrid-Empfehlung (für uns)

| Layer | Quelle | Empfehlung |
|-------|--------|------------|
| Ephemere Session-Todos | dsh `todo_write` | **Übernehmen** (leicht) |
| Ongoing Goal + Bar | dsh `tool-goal` (+ optional Round-Driver später) | **Übernehmen** (Kern der gewünschten UX) |
| Plan-Mode | dsh | **Done** (soft prompt + tools + banner) |
| Persistente Tasks | AL `agent_tasks` | **Behalten**, klar trennen („Backlog“ vs „Dieses Run“) |
| Activity-UI | AL Events + dsh-Labels | **UI upgraden** auf bestehende WS-Events |
| Compaction/Meter | AL Ist | **Nicht** dsh-portieren |
| MCP | AL stdio + streamable-http | Allowlist live; HTTP via `transport` |

---

## Abarbeiten — priorisierte Backlog

### P0 — Sofort / klein (Hygiene)

- [x] **MCP Allowlist** von toten `coding,coding_plan` auf live Agents — done
- [x] **Vision-Attach gate:** Image-Button / Attach filter when no VLM — done
- [x] Stale Mentions: Coding/Subagent-Toggle-Copy — done (partial)

### P1 — Conversation Goal + Todos (Backend)

- [x] Domain + migration `session_goal` / `session_todos`
- [x] Tools: `goal_*` / `todo_*`
- [x] Persistence + WS `agent.goal` / `agent.todos`
- [x] HTTP `PATCH /v1/user/conversations/{id}/goal` (Goal-Bar) + Snapshot in `GET /v1/chat/runtime`.
      Anlegen von Goals und Todo-Writes laufen ausschließlich über Tools, daher ohne HTTP-Fläche.
- [x] Agent-Prompt-Hinweis — `conversation_goal_prompt_block` injiziert Nutzungsregeln **und** den aktuellen
      Goal/Todo-State pro Turn (nur für Agents, die die Tools wirklich haben)
- [x] Trennung von `agent_tasks` dokumentiert in Tool-Description + Plan

### P2 — Chat-UI

- [x] **Ongoing Goal Bar**
- [x] **To-dos Panel**
- [x] Activity kinds Goal/Todos/Think labels
- [x] Live WS updates

### P3 — Optional / später

- [x] Plan-Mode (soft prompt + `plan_mode_set` / `exit_plan_mode` + UI-Banner)
- [x] Goal Round-Driver (`agent.goal_round` → UI auto-continue)
- [ ] Compaction-Drifts
- [x] MCP HTTP (`transport: streamable-http`)
- ~~Externe dsh-Schnittstelle~~ — **won't do** (kein Control-Plane zu externem Coding-Harness)

### Bewusst **nicht**

- ~~Coding-Agent / Shell / Workspace zurück.~~ — **revidiert 2026-09-07:** Coding ist zurück und nutzt dieselbe Harness.
- dsh Token-Meter oder Surface-`<compacted-summary>` 1:1.
- Kernel-Sandbox-Port.
- Externe dsh-Orchestrierungs-/Control-Plane-Schnittstelle.

---

## Vorgeschlagene Umsetzungsschritte (Reihenfolge)

```
1. P0 MCP Allowlist + Vision disable
2. P1 Todo tools + Session state + WS
3. P1 Goal tools + Session state + WS
4. P2 Goal Bar + Todos Panel
5. P2 Activity-Stream Labels + Think-Zeilen
6. Prompt/Policy polish + Tests
7. (optional) Plan-Mode / Goal Round-Driver
```

**Abhängigkeit UI ↔ Backend:** Bar/Panel brauchen Goal/Todo-State + Events; Activity-Polish kann parallel an bestehenden Events starten.

---

## Erfolgskriterien

- Langer Lauf: User sieht **ein** Ongoing Goal, Todos aktualisieren sich live, Activity liest sich wie Think → Tool → Done.
- Ohne VLM: Image-Attach nicht klickbar.
- MCP: mit `AGENT_MCP_ENABLED` und Server-Config an `general` (o.ä.) nutzbar.
- `agent_tasks`-Dashboard unverändert nutzbar; keine Vermischung der Begriffe in der UI.

---

## Referenzen

- dsh Goal: `deepseek-harness-master/packages/goal/` (`tool-goal`, `goal-round-driver`)
- dsh Todos: `packages/todo/tool-todo/`
- dsh Plan: `packages/plan/plan-mode/`
- AL Activity: `apps/frontend/src/features/chat/AgentActivityPanel.tsx`, `agentChatWsCore.ts`
- AL Tasks (Produkt): `plugins/tools/platform/tasks/agent_tasks.py`
- Vergleich: `docs/planning/dsh-agentlayer-capability-comparison.md`
- Alter dsh-Plan (unverändert): `docs/planning/dsh-integration-plan.md`
