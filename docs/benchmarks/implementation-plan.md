# Agent tuning platform — implementation plan

Companion docs: [`api-surface.md`](./api-surface.md), [`schemas/openapi.yaml`](./schemas/openapi.yaml), [`knob-registry.yaml`](./knob-registry.yaml).

---

## 1. Reviewer agent — yes, but separate from Operator

### Recommendation

**Add a dedicated `reviewer` agent** (`plugins/agents/reviewer/`). Do **not** overload Operator with review responsibilities.

| Agent | Role | Writes config? | Writes review? | Typical user |
|-------|------|----------------|----------------|--------------|
| **Operator** | Actuator — patch knobs, run benchmarks, manage platform | **Yes** (`agent_config_apply`, `settings_patch`, …) | No | Admin doing ops |
| **Reviewer** | Auditor — analyze cohorts, compare experiments, verdict | **No** (draft/recommend only) | **Yes** (`review_submit`) | Admin or General delegating analysis |
| **Backend job** | Headless reviewer (`POST /benchmarks/review`) | Optional `auto_apply` flag (policy-gated) | Yes | Automation after benchmark |

### Why not only Operator?

- **Separation of duties:** the agent that *changed* config should not be the only one that *judges* the change.
- **Tool surface:** Reviewer gets **read-heavy** tools (analysis, changelog, traces, snapshots). Operator keeps **write** tools. Smaller, safer tool schemas per agent.
- **Prompting:** Reviewer system prompt optimizes for evidence, regression detection, and structured JSON verdicts — not for patching Discord tokens.

### Can Reviewer “review Operator”?

**Yes — by auditing Operator’s effects, not by chatting with Operator.**

Reviewer tools can:

- `GET /agent-config/changelog?actor_type=operator_agent` — what Operator changed
- `GET /benchmarks/experiments/{id}` — runs linked to Operator-driven sessions
- `GET /benchmarks/analysis` + `/cohorts/compare` — before/after metrics
- `GET /run-traces/runs/{id}` — deep-dive failed scenarios after Operator tuning

Reviewer does **not** call Operator tools or impersonate Operator. It reviews **artifacts** (changelog, fingerprints, benchmark results, traces).

### Delegation model

Same pattern as Operator today:

```yaml
# plugins/agents/reviewer/agent.yaml (planned)
id: reviewer
min_role: admin
admin_only_delegatable: true
delegatable: false
tool_capability_any:
  - review.benchmark
  - review.config
  - meta.inspect
  - knowledge.retrieve
```

- **General** can `delegate(agent_id=reviewer, …)` for admins (like Operator).
- Reviewer is **not** in standard delegatable set for normal users.
- Reviewer is **not** schedulable (like Operator).

### Three ways to run a review

```text
┌─────────────────────────────────────────────────────────────┐
│  Same domain logic: benchmarks_review_service.run_review() │
└────────────────────────────┬────────────────────────────────┘
                             │
     ┌───────────────────────┼───────────────────────┐
     │                       │                       │
 Admin UI              Reviewer agent          Backend job
 POST /review           review_submit tool      scheduler / webhook
     │                       │                       │
     └───────────────────────┴───────────────────────┘
                             │
                    benchmark_reviews table
                    optional → draft patches (human accept)
```

**Human always confirms accept/reject on experiment** unless explicit `auto_apply_recommended_patches` policy (off by default).

---

## 2. Agent & tool inventory (target)

### 2.1 Operator agent (extend existing)

Location: `plugins/tools/platform/operator/admin.py`

| Tool | HTTP | Phase |
|------|------|-------|
| `settings_get` / `settings_patch` | operator-settings | **live** |
| `external_llm_*`, `tools_catalog`, … | various | **live** |
| `agents_list` / `agents_get` | GET agents | 0.5 |
| `agent_config_knobs` | GET agent-config/knobs | 0.5 |
| `agent_config_apply` | POST agent-config/apply | 0.5 |
| `agent_config_snapshot` | GET snapshot | 1 |
| `agent_config_changelog` | GET changelog | 1 |
| `tuning_session_create` | POST sessions | 1 |
| `tuning_session_validate` | POST sessions/validate | 1 |
| `tuning_session_close` | POST sessions/close | 1 |
| `benchmark_run_start` / `benchmark_run_get` | POST/GET runs | 0.5 |
| `benchmark_experiment_create` | POST experiments | 4 |
| `benchmark_experiment_run` | POST experiments/run | 4 |

Operator does **not** get `review_submit` (avoid self-review).

### 2.2 Reviewer agent (new)

Location: `plugins/tools/platform/reviewer/` (new package)

| Tool | HTTP | Write? |
|------|------|--------|
| `benchmark_analysis_get` | GET benchmarks/analysis | read |
| `benchmark_cohorts_list` | GET benchmarks/cohorts | read |
| `benchmark_cohort_compare` | GET benchmarks/cohorts/compare | read |
| `benchmark_stats_get` | GET benchmarks/stats | read |
| `benchmark_experiment_get` | GET experiments/{id} | read |
| `benchmark_experiment_report` | GET experiments/{id}/report | read |
| `benchmark_run_get` | GET runs/{id} | read |
| `benchmark_run_export` | GET runs/{id}/export | read |
| `agent_config_snapshot` | GET snapshot | read |
| `agent_config_fingerprint` | GET fingerprint | read |
| `agent_config_changelog` | GET changelog | read |
| `run_trace_get` | GET run-traces/runs/{id} | read |
| `agents_get` | GET agents/{id} | read |
| `review_submit` | POST benchmarks/review | **writes review record** |
| `review_get` | GET benchmarks/reviews/{id} | read |
| `review_recommend_patches` | POST agent-config/draft | draft only, no apply |

Capability gate: `review.benchmark`, `review.config` in tool metadata.

### 2.3 General agent (unchanged tools)

General keeps `delegate` → can invoke **reviewer** or **operator** for admin users. No new tools on General.

---

## 3. Interface checklist — what still needs building

### 3.1 Backend APIs

| ID | Endpoint / module | Status | Phase |
|----|-------------------|--------|-------|
| A1 | Registry loader (`knob-registry.yaml` → Pydantic) | **todo** | 0.5 |
| A2 | `GET /v1/admin/agent-config/knobs` | **todo** | 0.5 |
| A3 | `GET /v1/admin/agent-config/knobs/{knob_id}` | **todo** | 0.5 |
| A4 | DB `agent_config_overrides` + effective resolver | **todo** | 0.5 |
| A5 | `POST /v1/admin/agent-config/apply` | **todo** | 0.5 |
| A6 | `POST /v1/admin/agent-config/draft` | **todo** | 0.5 |
| A7 | `compute_agent_config_fingerprint()` | **todo** | 1 |
| A8 | `GET /fingerprint`, `GET /snapshot` | **todo** | 1 |
| A9 | `agent_config_changelog` table + `GET /changelog` | **todo** | 1 |
| A10 | `agent_config_sessions` + session CRUD + validate/close | **todo** | 1 |
| A11 | `benchmark_runs.cohort_json` migration | **todo** | 1 |
| A12 | `GET /benchmarks/analysis` + `patterns.py` | **todo** | 2 |
| A13 | `GET /benchmarks/cohorts`, `/cohorts/compare` | **todo** | 2 |
| A14 | Stats filters `cohort`, `fingerprint` | **todo** | 2 |
| A15 | `GET /benchmarks/runs/{id}/export` | **todo** | 2 |
| A16 | `benchmark_experiments` CRUD | **todo** | 4 |
| A17 | `POST /experiments/{id}/run` | **todo** | 4 |
| A18 | `benchmark_reviews` + `POST /review`, `GET /reviews/{id}` | **todo** | 5 |
| A19 | Extend `StartBenchmarkBody` (cohort, experiment, harness_preset) | **todo** | 4 |
| A20 | Git webhook / schedules (optional) | **todo** | 6 |

### 3.2 Operator tools (mirror HTTP)

| ID | Tool | Phase |
|----|------|-------|
| O1 | `agents_list`, `agents_get` | 0.5 |
| O2 | `agent_config_knobs`, `agent_config_apply` | 0.5 |
| O3 | **`benchmark_run_start`**, **`benchmark_run_get`** | 0.5 — Operator starts bench **when user asks in chat** |
| O4 | Session + changelog tools | 1 |
| O5 | Experiment tools | 4 |

### 3.3 Reviewer agent (new)

| ID | Item | Phase |
|----|------|-------|
| R1 | `plugins/agents/reviewer/agent.yaml` + system prompt | 5 |
| R2 | `plugins/tools/platform/reviewer/` tool package | 5 |
| R3 | Router yaml + capability `review.benchmark` | 5 |
| R4 | Register in agent registry; admin delegatable | 5 |
| R5 | Unit tests: reviewer cannot call apply | 5 |

### 3.4 Frontend

| ID | UI | Phase |
|----|-----|-------|
| F1 | Agent tuning tab (knobs from API) | 0.5–3 |
| F2 | Session workflow | 1 |
| F3 | Changelog + fingerprint display | 1 |
| F4 | Analysis / cluster view | 2 |
| F5 | Experiments list + detail | 4 |
| F6 | Review panel (verdict + accept/reject) | 5 |
| F7 | Reviewer chat entry (delegate or direct) | 5 |

### 3.5 Schemas & contracts

| ID | Item | Status |
|----|------|--------|
| S1 | OpenAPI fragment [`schemas/openapi.yaml`](./schemas/openapi.yaml) | **this PR** |
| S2 | JSON Schema for review input/output | **in openapi** |
| S3 | Knob registry JSON Schema (validate yaml) | **todo** |
| S4 | ADR `0008-agent-config-experiments.md` | **todo** |

---

## 4. Phased delivery

See **[`PLANNING.md`](./PLANNING.md) §1–3** for build order and **on-demand Operator chat** (benchmark only when user asks).

### Phase 0.5 — Minimum viable tuning API (2–3 weeks)

**Goal:** Change routing knobs at runtime; Operator can apply; benchmark validates.

1. A1–A5, A2–A3, O1–O2, O3  
2. Migrate first **runtime_config** knobs to DB effective config (e.g. max_tool_rounds, ranking)  
3. F1 read-only knob browser  

**Exit criteria:** Operator chat: “set max_tool_rounds to 12 and run routing-core” works end-to-end (apply → bench → poll → report).

### Operator chat — minimum tool chain (Phase 0.5)

Documented in [`PLANNING.md`](./PLANNING.md) §3. Required tools before chat-based tuning works:

1. `agent_config_knobs` — read effective values  
2. `agent_config_apply` — patch DB only (default; **no** benchmark unless user asked)  
3. `benchmark_run_start` — **only if user message requests a run**  
4. `benchmark_run_get` — poll when user wants status/results  

Operator must **not** call `benchmark_run_start` after apply unless the user asked for a benchmark (or confirmed when prompted).

### Phase 1 — Fingerprint & sessions (1–2 weeks)

1. A7–A11, A10, O4, F2–F3  
2. Every apply writes changelog + fingerprint  
3. Benchmark runs store `cohort_json`  

**Exit criteria:** Compare two runs by fingerprint in API.

### Phase 2 — Analysis (1–2 weeks)

1. A12–A15, A14, F4  
2. `patterns.py` integrated  

**Exit criteria:** `GET /analysis?cohort=…` returns cluster breakdown.

### Phase 3 — Knob UI (1–2 weeks)

1. Full registry in UI; grouped apply  
2. Read-only code/rubric knobs with git hash  

### Phase 4 — Experiments (1 week)

1. A16–A17, A19, O5, F5  
2. Suite/harness presets from registry  

**Exit criteria:** Experiment lifecycle draft → run → completed.

### Phase 5 — Reviewer agent + review API (1–2 weeks)

1. A18, R1–R5, F6–F7  
2. Shared `benchmarks_review_service` for HTTP + tool  
3. Reviewer agent live; Operator changes auditable via changelog  

**Exit criteria:** After Operator tuning session, delegate to Reviewer → structured verdict → human accept on experiment.

### Phase 6 — Automation (optional)

1. A20, nightly schedules, CI webhook  

---

## 5. Security & policy

| Rule | Detail |
|------|--------|
| Reviewer read-only on config | No `apply`, no `settings_patch` on reviewer tool allowlist |
| Operator cannot `review_submit` | Prevents self-review loop |
| `auto_apply_recommended_patches` | Default `false`; tenant policy flag |
| All writes audited | `actor.type`: `user`, `operator_agent`, `reviewer_job`, `reviewer_agent` |
| Admin only | All `/v1/admin/agent-config/*`, review APIs, both agents |

---

## 6. References

| Doc | Content |
|-----|---------|
| [`schemas/openapi.yaml`](./schemas/openapi.yaml) | Request/response schemas |
| [`api-surface.md`](./api-surface.md) | Endpoint narrative + flows |
| [`agent-tuning-platform.md`](./agent-tuning-platform.md) | Product design |
