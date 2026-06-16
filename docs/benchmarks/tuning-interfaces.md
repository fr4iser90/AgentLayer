# Agent tuning interfaces — semantic layer

**Planning status: complete (v2).** Index: [`PLANNING.md`](./PLANNING.md).

**Not HTTP.** Maps **what** you tune (tool routing, prompts, routers, …) to code paths and **value schemas**.

Transport layer: [`api-surface.md`](./api-surface.md), [`schemas/openapi.yaml`](./schemas/openapi.yaml).

Knob catalog with types: [`knob-registry.yaml`](./knob-registry.yaml) (v2).

Value JSON Schemas: [`schemas/interfaces/`](./schemas/interfaces/).

---

## Schema status (v2 — complete)

| Layer | Value schema file | Apply path |
|-------|-------------------|------------|
| **runtime_config** | `schemas/interfaces/runtime-config-values.json` | `agent-config/apply` → **DB** (not `.env`) |
| agent_yaml | `schemas/interfaces/agent-yaml-fields.json` | `agent-config/apply` → DB overlay |
| router_yaml | `schemas/interfaces/router-overlay.json` | `agent-config/apply` → DB overlay |
| operator | `schemas/interfaces/operator-tuning-fields.json` | `operator-settings` (live) |
| bench | `schemas/interfaces/bench-harness.json` | `benchmarks/runs` (per run) |
| code, rubric | `schemas/interfaces/read-only-fingerprint.json` | none (hash only) |

**Policy:** `.env` / `bootstrap_env_key` = install default only. Tuning **never** edits env. See registry header in `knob-registry.yaml`.

---

## Interface map (10 groups)

### 1. Agent loop limits (`agent_limits`)

| knob_id | What | Code | Value schema today |
|---------|------|------|-------------------|
| `agent.max_tool_rounds` | Max LLM↔tool rounds | `config.py` → `AGENT_MAX_TOOL_ROUNDS` | int, implicit (1…cap) |
| `agent.subagent_max_tool_rounds` | Subagent rounds | `config.py` | int, implicit |
| `agent.subagent_timeout_sec` | Delegate timeout | `config.py` | int/float, implicit |
| `agent.tool_choice_required_retry` | Retry if tool required | `config.py` | bool, implicit |

**Target schema:** `integer` with min/max in registry; apply via `agent-config/apply`.

---

### 2. Tool routing (`tool_routing`)

| knob_id | What | Code | Value schema today |
|---------|------|------|-------------------|
| `tool_routing.domain_order` | `AGENT_TOOL_DOMAIN_ORDER` | `tool_routing.py` | comma-separated string → list |
| `tool_routing.router_strict_default` | Strict category filter | `tool_routing.py` + env | bool |
| `tool_routing.classify_categories` | Trigger → category logic | `plugin_system/tool_routing.py` | **code only** — hash in fingerprint |

**Target schema (tunable params):** `domain_order` → `string_list` of known domain ids; `router_strict_default` → `boolean`.

---

### 3. Tool forward (`tool_forward`)

| knob_id | What | Code | Value schema today |
|---------|------|------|-------------------|
| `tool_forward.ranking_enabled` | Rank/prune tools per round | env + `tool_forward_policy.py` | bool |
| `tool_forward.full_schema` | Full JSON schema to LLM | env | bool |
| `tool_forward.catalog_after_first_round` | Promote catalog after R1 | env | bool |
| `tool_forward.policy` | Pinning, delegate preserve | `tool_forward_policy.py` | **code only** |

**Target schema:** booleans for env knobs; policy code = git + content hash.

---

### 4. Agents & prompts (`agents`)

| knob_id | What | Code / file | Value schema today |
|---------|------|-------------|-------------------|
| `agent.general.pinned_tools` | Tools always forwarded | `plugins/agents/general/agent.yaml` | **string list**, implicit in loader |
| `agent.general.system_prompt` | Orchestrator prompt | `plugins/agents/general/system_prompt.md` | **markdown string**, no max length schema |
| `operator.delegate_enabled` | Kill-switch (planned) | operator_settings (planned) | bool (not in DB yet) |

**Example today (YAML, not JSON Schema):**

```yaml
# plugins/agents/general/agent.yaml
pinned_tools:
  - delegate
  - catalog
  - workspace.create
```

**Target schema:**

```yaml
# knob-registry.yaml (planned fields per knob)
- id: agent.general.pinned_tools
  type: string_list
  items_enum: tool_names   # or dynamic from GET /v1/admin/tools
- id: agent.general.system_prompt
  type: string
  format: markdown
  maxLength: 32000
```

**Also in agent.yaml (not all in registry v1):** `tool_allowlist`, `tool_domains`, `model_profile`, `tool_discipline_preset` — loader: `agent_plugin_loader.py`.

---

### 5. Routers (`routers`)

| knob_id | What | File | Value schema today |
|---------|------|------|-------------------|
| `router.delegate` | Delegate routing phrases/rules | `delegate.router.yaml` + `delegate.py` | **no schema** — locale phrase maps |
| `router.catalog` | Catalog router | `catalog.router.yaml` | same |
| `router.task` | Task router | `task.router.yaml` | same |

**Example (phrases only in yaml today):**

```yaml
domain: delegate
phrases:
  en: [delegate, subagent, specialist]
  de: [...]
```

**Target schema (planned):** JSON Schema for router overlay document `{ domain, phrases: { locale: string[] } }` or structured routing rules when delegate logic moves partially to DB.

---

### 6. Model routing (`model_routing`)

| knob_id | What | Code | Value schema today |
|---------|------|------|-------------------|
| `model.resolve_effective` | Subagent model inheritance | `model_routing.py` | **code only** |

Tuning = code changes + `model_profile` in agent yaml (implicit string enum per agent).

---

### 7. Planner (`tool_routing` / code)

| knob_id | What | Code | Value schema today |
|---------|------|------|-------------------|
| `planner.tool_merge` | Merge/routing in chat loop | `agent_planner.py` | **code only** |

---

### 8. Smart route (`smart_route`)

| knob_id | What | Code | Value schema today |
|---------|------|------|-------------------|
| `operator.llm_smart_routing_enabled` | Chat model routing | `llm_smart_route.py` + operator_settings | **Yes** — fields on `OperatorSettingsPatch` |

Related fields (all in `OperatorSettingsPatch`): `llm_router_model`, `llm_router_local_confidence_min`, `llm_route_*`, `llm_queue_*`.

---

### 9. Benchmark rubrics (`rubrics`)

| knob_id | What | Code | Value schema today |
|---------|------|------|-------------------|
| `rubric.s1_tool_catalog` | S1 pass criteria | `tests/benchmarks/agent/rubrics.py` | **code** |
| `rubric.s4_delegate_math` | S4 pass criteria | same | **code** |

Fingerprint stores file hash; not runtime-tunable via API.

---

### 10. Benchmark harness (`bench_harness`)

| knob_id | What | Code | Value schema today |
|---------|------|------|-------------------|
| `bench.scenario_timeout_sec` | Per-scenario timeout | `StartBenchmarkBody.scenario_timeout_sec` | **Yes** — Pydantic `ge=30, le=86400` |
| `bench.max_tool_rounds_override` | Bench-only rounds | `StartBenchmarkBody` | **Yes** — `ge=1, le=512` |
| `bench.capture_timeline` | WS timeline | harness env | string/bool implicit |
| `bench.harness_preset` | observability / chat_parity | planned | enum (planned) |

---

## Where schemas live

```text
docs/benchmarks/
├── PLANNING.md                     ← START HERE
├── knob-registry.yaml              ← v2: every knob + value_schema ref
├── schemas/
│   ├── knob-registry.schema.json
│   ├── openapi.yaml                ← HTTP transport
│   └── interfaces/                 ← VALUE schemas ✅
│       ├── runtime-config-values.json
│       ├── agent-yaml-fields.json
│       ├── router-overlay.json
│       ├── bench-harness.json
│       ├── operator-tuning-fields.json
│       └── read-only-fingerprint.json
```

---

## Summary table (v2)

| Semantic interface | Registry | Value schema | Apply via |
|--------------------|----------|--------------|-----------|
| Agent limits | yes | runtime-config-values.json | agent-config/apply → DB |
| Tool routing (runtime) | yes | runtime-config-values.json | agent-config/apply → DB |
| Tool routing (code) | yes | read-only-fingerprint | git |
| Tool forward (runtime) | yes | runtime-config-values.json | agent-config/apply → DB |
| Tool forward (code) | yes | read-only-fingerprint | git |
| System prompts & pins | yes | agent-yaml-fields.json | agent-config/apply |
| Routers | yes | router-overlay.json | agent-config/apply |
| Model routing | yes | read-only-fingerprint | git |
| Smart route | yes | operator-tuning-fields.json | operator-settings (live) |
| Rubrics | yes | read-only-fingerprint | git |
| Bench harness | yes | bench-harness.json | benchmarks/runs |

**Planning for this layer: complete.** See [`PLANNING.md`](./PLANNING.md).
