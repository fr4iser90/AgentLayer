Hier ist ein **kompletter Umsetzungsplan** — von Quick Wins bis dynamischem Tool-Budget. Er baut auf eurem bestehenden Code auf (`agent_planner.py`, `agent_tools.py`, `agent_registry.py`, `agent_prompts.py`, `context_budget`).

---

# AgentLayer: Professionelles & dynamisches Tool-System

## Zielbild

**Nicht:** „Alle Tools, Ranking, hoffen.“  
**Sondern:** Pro Turn ein **kleines, vorhersagbares, budgetiertes** Tool-Set — abhängig von Agent, Task, Modell und verbleibendem Context.

```
Allowlist (Agent) → Pins (immer) → Task-Filter → Ranking (Rest) → Schema-Tier → LLM
         ↑                                                              ↓
    context_window + model_tier + live prompt_tokens ←── Feedback nächste Runde
```

---

## Design-Prinzipien

1. **Agent = schmale Domäne** (Dashboard ≠ Pets + RSS + … in einem Turn)
2. **Pins > Ranking** (kritische Tools nie wegranken)
3. **Budget in Tokens**, nicht fixe „10“
4. **Schema-Tiers** (full / catalog / help-on-demand)
5. **Model-Tier** begrenzt *Qualität*, Context begrenzt *Menge*
6. **Observability** — jeder Turn loggt: allowlist → forward → budget → schema mode

---

## Phase 0 — Quick Wins (1–2 Tage, hoher Impact)

*Kein neues Budget-System, sofort stabiler Dashboard-Chat.*

| # | Maßnahme | Wo |
|---|----------|-----|
| 0.1 | Dashboard `agent.yaml`: `tool_domains: [dashboard]` (+ optional `projects`) | `plugins/agents/dashboard/agent.yaml` |
| 0.2 | **Pins** für `dashboard`: `read`, `propose_layouts`, `patch_layout`, `patch_data`, `list` | `agent_tools.py` → `_pinned_tools_for_agent` |
| 0.3 | **`tool_discipline_preset: dashboard`** — kein JSON im Text, Layout → `propose_layouts` | `agent_prompts.py`, `agent.yaml` |
| 0.4 | Tool-Triggers für Ranking (`layout`, `variant`, `vorschlag`, …) | `dashboard.py` `TOOL_TRIGGERS` + Ranking in `agent_tools.py` |
| 0.5 | `.env.example`: dokumentieren `AGENT_TOOLS_MAX_RANKING`, `AGENT_CONTENT_TOOL_FALLBACK` | `.env.example` |
| 0.6 | Operator-Default oder Doc: schwache lokale Modelle → `AGENT_CONTENT_TOOL_FALLBACK=true` | docs |

**Erfolg:** Layout-Anfrage → `read` + `propose_layouts` immer in `tools[]`; Karten erscheinen bei funktionierendem Tool-Calling.

---

## Phase 1 — Tool-Forward-Policy (Kern, ~1 Woche)

Neues Modul: **`apps/backend/domain/tool_forward_policy.py`**

### 1.1 Eingaben (`ToolForwardContext`)

```python
@dataclass
class ToolForwardContext:
    agent_id: str | None
    model_id: str
    context_window_tokens: int      # aus provider catalog / context_budget
    model_tier: str                 # strong | standard | weak_local
    user_text: str
    pinned_names: frozenset[str]
    allowlist_specs: list[dict]     # nach Agent-Filter
    prompt_tokens_so_far: int | None  # letzte LLM-Runde
    round_index: int
    full_schema_preference: bool    # body override / agent default
```

### 1.2 Ausgaben (`ToolForwardPlan`)

```python
@dataclass
class ToolForwardPlan:
    forward_specs: list[dict]
    forward_names: list[str]
    schema_mode_per_tool: dict[str, Literal["full", "catalog"]]
    budget_tokens_allocated: int
    budget_tokens_used_estimate: int
    max_tool_count: int
    ranking_applied: bool
    pins_included: list[str]
    meta: dict  # für WS event / logs
```

### 1.3 Algorithmus (Reihenfolge)

1. **Allowlist** — unverändert aus `agent_registry` + Filters (policy, disabled, dashboard `tool_allowlist`)
2. **Pins** — aus Agent-Plugin + optional `agent_pinned_tools` im Chat-Body
3. **Task hints** (optional Phase 2) — `agent_capability_hints`, Keywords
4. **Ranking** — nur auf `allowlist − pins`
5. **Budget-Cap** — fülle mit ranked Tools bis Budget oder `max_count`
6. **Schema-Tier** — Pins + Top-3 intent: `full`; Rest: `catalog` wenn Budget knapp

### 1.4 Integration

- `agent_planner.py`: Block ab Zeile ~827 (Ranking) ersetzen durch `build_tool_forward_plan()`
- `agent_io._tools_for_chat_request`: pro Tool `schema_mode` statt global bool
- WS-Event `agent.session`: `tool_forward_plan` Metadaten (Debug-UI)

### 1.5 Tests

- `tests/test_tool_forward_policy.py`: Pins immer drin; Budget 10% bei 262k; weak tier cap 8; `propose_layouts` full schema

---

## Phase 2 — Dynamisches Token-Budget (~1 Woche)

Neues Modul: **`apps/backend/infrastructure/tool_token_budget.py`**

### 2.1 Formel (konfigurierbar)

```env
AGENT_TOOLS_BUDGET_RATIO=0.10          # max Anteil context_window für tools[]
AGENT_TOOLS_BUDGET_MIN_TOKENS=4000
AGENT_TOOLS_BUDGET_MAX_TOKENS=32000
AGENT_TOOLS_COUNT_CAP_STRONG=25
AGENT_TOOLS_COUNT_CAP_STANDARD=15
AGENT_TOOLS_COUNT_CAP_WEAK=8
```

```text
raw_budget = clamp(ratio * context_window, min, max)
reserved = estimate_tokens(system + messages)   # tiktoken/chars/4
available = context_window - reserved - headroom_for_completion
tool_budget = min(raw_budget, available * 0.5)  # tools nicht alles fressen
max_count = min(count_cap[tier], floor(tool_budget / avg_tool_tokens))
```

### 2.2 Token-Schätzung pro Tool

- Cache pro `(tool_name, full|catalog)` aus serialisiertem JSON
- `_tools_payload_json_chars` → Tokens (~chars/4 oder tiktoken wenn verfügbar)
- Große Tools (`propose_layouts`) höher gewichten → weniger Begleit-Tools

### 2.3 Feedback pro Runde

Wenn `prompt_tokens > soft_limit` (bestehendes `ContextBudget`):

- Nächste Runde: nur Pins + 3 ranked
- oder catalog-only für alle außer Pins
- Discovery-Tools (`list_available_tools`, …) droppen

### 2.4 Abhängigkeit vom Modell

| Quelle | Nutzung |
|--------|---------|
| `GET /v1/models` / provider catalog | `context_window` |
| Operator-Setting oder Heuristik | `model_tier` |
| Live `usage.prompt_tokens` | Round-2-Anpassung |

**Model-Tier Heuristik (Start):**

- `weak_local`: Ollama, GGUF, kein zuverlässiges tool_calls in Tests
- `standard`: mittlere APIs
- `strong`: GPT-4 class, Claude, bekannte tool-native

Später: Operator UI „Tool-Calling: reliable / fallback / text-only“.

---

## Phase 3 — Agent- & Task-Modell (~1 Woche)

### 3.1 Agent-Plugin erweitern (`agent.yaml`)

```yaml
tool_domains:
  - dashboard
tool_domains_optional:    # nur bei capability hint / user intent
  - projects
pinned_tools:
  - read
  - propose_layouts
  - patch_layout
  - patch_data
  - list
tool_forward:
  max_tools_override: 12      # optional, sonst dynamisch
  prefer_full_schema: [propose_layouts, patch_layout]
  discovery_tools: false      # kein list_available_tools im Dashboard-Agent
tool_discipline_preset: dashboard
```

Loader: `agent_plugin_loader.py`, Registry: `agent_registry.py`.

### 3.2 Task-/Intent-Filter (leichtgewichtig)

Vor Ranking:

- Keywords in User-Text → boost Domain `dashboard` / Tools mit `TOOL_TRIGGERS`
- Optional kleines Embedding (bestehend) nur innerhalb Allowlist ≤20

**Layout-Intent:** force-include `read`, `propose_layouts` (zusätzlich zu Pins).

### 3.3 Sub-Agenten statt Mega-Allowlist

| Agent | Domains | Pins |
|-------|---------|------|
| `dashboard` | `dashboard` (+ `projects` optional) | Layout-Set |
| `general` | breit | `delegate` |
| `coding` | coding | read_file, … (besteht) |

Pets/Ideas/RSS **raus** aus Dashboard-Agent — eigene Agents oder General.

### 3.4 Board-Level Override (besteht)

`_agentlayer.tool_allowlist` — UI bleibt; Policy: `allowlist ∩ agent_allowlist`.

---

## Phase 4 — Schema-Strategie & Discovery (~3–5 Tage)

### 4.1 Drei Stufen

| Stufe | Wann | Inhalt |
|-------|------|--------|
| **Full** | Pins, Top-3, unattended scheduler | Volles JSON Schema |
| **Catalog** | Budget knapp, weak tier | Name + Beschreibung + `additionalProperties` |
| **Help** | Catalog-Tool vor komplexem Call | `get_tool_help` einmal (Discipline) |

`agent_prompts._tools_for_chat_request` → pro-spec `builder(name, fn, mode)`.

### 4.2 Wann Discovery erlauben

Nur wenn:

- `forward_count > budget_allowance` **und**
- Intent unklar **und**
- `discovery_tools: true` am Agent

Dashboard: **discovery_tools: false**.

### 4.3 Content-Tool-Fallback (schwache Modelle)

- Pro `model_tier=weak_local`: auto-enable Fallback oder Warnung in UI
- Metrik: `tool_calls_native` vs `tool_calls_synthetic` vs `text_only_json`

---

## Phase 5 — Observability & Operator-UI (~1 Woche)

### 5.1 Logging (structured)

Pro Run (`agent_run_id`):

```json
{
  "allowlist_count": 38,
  "after_filters": 12,
  "pins": ["read", "propose_layouts"],
  "ranked_in": 5,
  "forward_count": 7,
  "tool_budget_tokens": 18000,
  "tool_json_tokens_est": 9200,
  "schema_full": 3,
  "schema_catalog": 4,
  "model_tier": "weak_local",
  "context_window": 262144
}
```

Bereits teilweise: `tools_pipeline` Log — erweitern.

### 5.2 Admin / Debug

- Run-Traces UI: Tool-Forward-Plan anzeigen
- Optional Chat-Dev-Panel: „Tools this turn“

### 5.3 Operator Settings (optional)

- Global: `tools_budget_ratio`, default tier overrides
- Per Provider: tool_calling_tier

---

## Phase 6 — Dokumentation & Migration

| Doc | Inhalt |
|-----|--------|
| `docs/features/agent-tool-forward-policy.md` | Architektur, Formeln, Env |
| `docs/features/agent-registry-and-allowlists.md` | `pinned_tools`, `tool_forward` |
| `plugins/agents/dashboard/system_prompt.md` | An dynamische Policy anpassen |
| `.env.example` | Alle neuen `AGENT_TOOLS_*` |

**Migration:**

- Bestehende Env `AGENT_TOOLS_MAX_RANKING=10` → Fallback wenn `AGENT_TOOLS_BUDGET_RATIO` unset
- Kein DB-Migration nötig
- Dashboard-Agent-YAML-Änderung = Verhalten ändert sich — Release Note

---

## Implementierungsreihenfolge (empfohlen)

```text
Sprint A (sofort):     Phase 0
Sprint B:            Phase 1.1–1.5 (Policy + Pins in Code)
Sprint C:            Phase 2 (Budget + model_tier)
Sprint D:            Phase 3 (agent.yaml Felder + Dashboard schlank)
Sprint E:            Phase 4 (per-tool schema)
Sprint F:            Phase 5 (Observability)
```

Parallel: Dashboard Layout-Karten (bereits gebaut) profitieren ab **Sprint A**.

---

## Erfolgskriterien

| Metrik | Ziel |
|--------|------|
| Dashboard Layout-Request | `propose_layouts` in ≥95% Runs in `tools[]` |
| Tool-Ausführung | ≥80% mit native/synthetic tool_calls, nicht Text-JSON |
| `dashboard.read` bei Layout-Flow | immer in forward set |
| P95 tool JSON size | < 10% context_window |
| User-visible JSON tool blobs | < 5% Assistant messages |

---

## Was du **nicht** tun solltest

- Nur `AGENT_TOOLS_MAX_RANKING=50` drehen ohne Pins
- Ranking über 38 Tools als einzige Strategie
- Full schema für alle Tools bei weak local models
- Discovery-Tools im Embedded Dashboard-Chat

---

## Kurz: Antwort auf deine Kernfrage

**Ja**, professionell = **dynamisch nach Modell + Context + Task**.  
**Nein**, fix 10 ist kein Endzustand.  
**Ja**, „~10 % Context für Tools“ ist eine gute **Obergrenze**, kombiniert mit **Count-Cap pro model_tier** und **Pins**.

Big Player gewinnen vor allem durch **kleine Agent-Surfaces**, nicht durch riesige Tool-Listen im selben Call.

---

Wenn du in **Agent-Mode** wechselst, kann ich mit **Phase 0 + Phase 1** starten (Pins, schlanker Dashboard-Agent, `tool_forward_policy.py` Grundgerüst) — das ist der beste ROI für dein Layout-Problem. Optional kann der Plan auch als `docs/planning/agent-tool-forward-policy.md` ins Repo.