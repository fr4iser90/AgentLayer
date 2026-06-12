# Benchmark pattern analysis & weak-model compatibility (roadmap)

**Status:** design / documentation only — no implementation yet.

This document captures how we want to **analyse recurring failure patterns** across LLM providers (especially local models with poor tool-calling training), and what **backend or harness layers** could do later so those models remain usable without polluting production behaviour.

Related: [`agent-llm-benchmark.md`](./agent-llm-benchmark.md), failure export fields in `tests/benchmarks/agent/harness.py`, Admin run detail `bench_diagnostics`.

---

## 1. Problem statement

Not all models implement OpenAI-style tool calling reliably. In benchmarks we already see classes of failure that are **not product bugs** but **model / format mismatches**:

| Symptom | Example | Rubric often says |
|---------|---------|-------------------|
| **Fake tool calling** | Tool call described in prose (`I'll call workspace.create…`) but no `tool_calls` in the API response | `read_file not used`, timeout |
| **Wrong tool name** | `workspaces.create` vs `workspace.create`, hallucinated plugin names | tool rejected / not in catalog |
| **Malformed arguments** | JSON in markdown fence, empty `{}`, string instead of object | schema validation / reject |
| **Argument shape drift** | `git_url` missing, `name` without `bench-…` prefix, wrong branch | workspace not found, quota noise |
| **Loop / search spiral** | repeated `list_tools_in_category`, `repository.search` without progress | latency rubric, cancel |
| **Reply without terminal answer** | endless `42` repetition (S2), reasoning leak into content | latency / content rubric |
| **Delegate misuse** | calls `write_file` on general surface instead of `delegate` | rubric / git outcome |
| **Transport vs rubric** | `cancelled` + 360s timeout vs wrong answer | need split classification |

Goal for **pattern analysis**: automatically group failures by **mechanism** (why / how), per **model profile**, so we can decide whether to fix prompts, rubrics, backend shims, or exclude a model from a tier.

---

## 2. What we already capture (baseline)

Use this as the data source for future analysers — **extend, don’t replace**.

### Per-scenario result (`ScenarioResult` / Admin export)

- `tool_names`, `tool_call_count`, `llm_round_count`, `latency_ms`
- `transport_error`, `rubric_failure_reason`, `failure_reason`, `assistant_excerpt`
- `agent_id`, `effective_agent_id`, `forwarded_tool_count`, `forwarded_tools`
- `expected_workspace_name`, `workspace_create_name`, `delegate_call_count`, `subagent_start_count`
- `ws_errors` (e.g. `agent.aborted: cancelled`)

### WebSocket timeline (`run_metrics.bench_diagnostics`)

- `tool_rounds[]`: round, name, `rejected`, `ok`, `error`, `wire_arguments`, `normalized_arguments`, `validation`
- `schema_rounds[]`: when full schema was promoted after reject
- `timeline_tail`, `event_counts`, `llm_stream` (text / reasoning excerpts)
- `session`: forwarded tools, `effective_agent_id`, routed category

### Run-level

- `bench_cleanup` / `bench_cleanup_finish` (quota / sandbox)
- `benchmark_run_id` DB markers on workspaces, dashboards, conversations (see migration `schema_093`)

**Gap today:** no single **failure_class** or **pattern_id** on each result — classification is manual from export JSON.

---

## 3. Target taxonomy (failure patterns)

Proposed stable labels for aggregation and dashboards. One scenario run may have **primary** + **secondary** tags.

### A. Model output format

- `A1_prose_instead_of_tool_call` — describes tools in natural language only
- `A2_tool_name_hallucination` — name not in registry / typo
- `A3_malformed_tool_arguments` — non-JSON, wrong type, empty args
- `A4_wrong_tool_surface` — coding tool on general agent (or inverse)
- `A5_stream_garbage` — repetition, reasoning in content channel, no stop

### B. Tool loop behaviour

- `B1_catalog_loop` — introspection tools only, no product action
- `B2_search_loop` — search/list_dir without read/delegate/write
- `B3_retry_after_reject` — recoverable after schema promotion vs not
- `B4_max_rounds_exhausted` — hit `agent_max_tool_rounds`

### C. Environment / sandbox

- `C1_workspace_quota` — user or benchmark quota (split via marker + API)
- `C2_workspace_name_mismatch` — create/bind name ≠ rubric expectation
- `C3_workspace_create_failed` — explicit tool error in excerpt
- `C4_fixture_skip` — secrets / friends missing

### D. Rubric / task

- `D1_correct_tools_wrong_outcome` — tools ok, git/file/dashboard check failed
- `D2_latency` — slow but possibly correct path
- `D3_cancelled` — admin timeout / cancel

### E. Backend / routing (investigate, not blame model)

- `E1_delegate_dropped_from_tools` — ranking removed `delegate`
- `E2_effective_agent_override` — coding forced to general on chat surface
- `E3_forwarded_tool_set_too_small` — capability routing over-pruned

Pattern rules should be **pure functions** over existing export + diagnostics (unit-testable with fixtures from real failed runs).

---

## 4. Pattern analysis pipeline (future)

```
benchmark run JSON / DB
    → per-result feature extractors (tool_rounds, excerpt, rubric)
    → classify (primary pattern + confidence)
    → aggregate by (suite, scenario, profile_label, model)
    → report: top patterns, example run_ids, suggested mitigation
```

### Outputs (later)

- **Admin:** “Failure patterns” tab on run compare — bar chart by `pattern_id`
- **CI / nightly:** regression on pattern *rates* (not only pass/fail)
- **Model card:** “Known weaknesses” for Qwen3.6-35B local — e.g. 40% `A1`, 25% `B1`

### Non-goals (v1 analysis)

- No automatic prompt rewriting
- No automatic backend shim enable per model without operator toggle
- No ML classifier required — start with rule-based taxonomy above

---

## 5. Compatibility layers for weak models (options)

When analysis shows a pattern is **systematic for a model family**, mitigations fall into layers. Prefer **narrow, benchmark-visible or profile-scoped** changes before global production hacks.

### Layer 0 — Measurement only (current direction)

- Rich failure export + diagnostics
- Separate benchmark workspace quota (DB marker)
- Skip scenarios when sandbox full (fail fast)

### Layer 1 — Harness / rubric (cheap)

- Scenario-specific latency caps per profile (e.g. local 35B &gt; 30s for S2)
- Rubric accepts alternate success paths already started (`delegate` OR direct tool)
- Explicit “pattern-aware” skip: don’t count `C1` against model score in compare view

### Layer 2 — Prompt & tool presentation (agent config)

- Profile-specific system nudges in manifest (`profiles.yaml`): “You MUST emit tool_calls, never describe tools in prose”
- Pin critical tools in allowlist for General (`delegate`, `workspace.create`) — policy in `tool_forward_policy.py`
- Stronger catalog / `get_tool_help` examples for weak models

### Layer 3 — Backend normalisation shim (compatibility)

Applied **only when** `benchmark_run_id` set or `agent_tools_full_schema` / profile flag — avoids changing prod chat for all users.

| Technique | Helps with | Risk |
|-----------|------------|------|
| **Prose → tool call extractor** | A1 | false positives, security |
| **Fuzzy tool name map** | A2 | wrong tool invoked |
| **Argument repair** (fill `name` from prompt prefix, default `bind=true`) | A3, C2 | hides real model gap |
| **Forced `tool_choice` for step 1** | W1 “must create workspace first” | rigid, breaks multi-step |
| **Auto-retry round with full schema** | B3 | latency, already partial via schema_rounds |
| **Circuit breaker** on catalog loop | B1 | may stop valid exploration |
| **Sub-agent routing** (“always delegate writes”) | A4 | already product direction for General |

**Recommendation:** implement shims behind **explicit flags** (`agent_bench_compat_mode`, per-profile manifest `compat: fake_tool_repair`) and log every repair in `bench_diagnostics` as `compat_action` for audit.

### Layer 4 — Model routing (product)

- Exclude model from tier 3–4 in Admin compare
- Route small/local models to **math / no-tool** scenarios only
- Separate “tool calling certification” suite before enabling coding benchmarks

---

## 6. Decision guide: shim vs train vs exclude

| If pattern is… | Prefer |
|----------------|--------|
| Rare, one-off | Rubric + doc only |
| Quota / sandbox (`C*`) | Infra cleanup + DB marker (done) |
| `A1`–`A3` &gt; 20% on a local model | Layer 3 shim **in benchmark only** + report |
| `B1` catalog loop | Pin tools + circuit breaker in ranking |
| `E*` backend | Fix routing — **not** model blame |
| Still &gt; X% after shims | Exclude from tier or change model |

---

## 7. Open questions (for when we implement)

1. **Profile-level compat flags** in `benchmarks/manifests/_profiles.yaml` vs global operator setting?
2. **Store `pattern_id` on `ScenarioResult`** in DB vs offline analyser script only?
3. **Cross-run compare:** same model after prompt change — diff pattern rates?
4. **Fake tool calling detection:** regex on excerpt vs compare `assistant` text to `tool_rounds` length?
5. **Security boundary:** prose extractor must never run shell/bash from fenced code in weak models.

---

## 8. Suggested first implementation slice (when prioritized)

1. `tests/benchmarks/agent/patterns.py` — rule-based `classify_failure(result) -> list[str]`
2. Unit tests with frozen excerpts from real exports (Qwen fake tools, quota, S2 spam)
3. Add `patterns: []` to failure CSV export
4. Admin: show primary pattern under each failed scenario
5. Only then: optional benchmark-only compat shim behind flag

---

## 9. References in codebase

| Area | Path |
|------|------|
| Failure export | `tests/benchmarks/agent/harness.py` (`failure_export_row`) |
| Rubrics | `tests/benchmarks/agent/rubrics.py` |
| Tool forward / ranking | `apps/backend/domain/tool_forward_policy.py`, `agent_planner.py` |
| Schema promotion after reject | `bench_diagnostics.tool_rounds`, `schema_rounds` |
| Workspace tool create | `plugins/tools/workspace/bind/workspaces.py` |
| Benchmark resources / quota | `apps/backend/infrastructure/benchmark_resource_service.py` |

---

**Summary:** Benchmarks should evolve from pass/fail to **labelled failure patterns**, then optionally apply **scoped compatibility layers** for weak local models — without hiding real product regressions (`E*`, `D1`) or weakening production chat defaults.
