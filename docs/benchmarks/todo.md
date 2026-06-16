# Benchmark / agent tuning — status

**Planning: v3.2.** [`PLANNING.md`](./PLANNING.md) — **you start** runs (Benchmarks page or LLM); **platform tracks** everything automatically.

**Implementation:** in progress — Phase 0.5–5 landed in code; run migration `schema_095` before use.

---

## Goal

Find the best **Agent-Layer configuration** across a model matrix. Patch when **you** want → benchmark when **you** want (page or LLM) → **tracking always automatic**. No system-started runs without you.

---

## Planning complete (see PLANNING.md)

| Topic | Section |
|-------|---------|
| Build order (Phases 0.5→6) | PLANNING — Build order |
| Who starts benchmarks | PLANNING — Workflow A / B |
| Automatic tracking | PLANNING — Core policy |
| LLM multi-variant loops | PLANNING — Workflow B |
| Live vs planned | PLANNING — Live vs planned |
| runtime_config → WebUI not `.env` | `knob-registry.yaml` header |

Artifacts: `knob-registry.yaml`, `schemas/`, `api-surface.md`, `implementation-plan.md`, …

---

## Implementation

- [x] **0.5** — agent-config API, DB (`schema_095`), Operator tools: apply + **benchmark_run_start/get**
- [x] **1** — fingerprint, sessions, changelog, cohort on runs
- [x] **2** — analysis + cohort compare API
- [x] **3** — Agent tuning WebUI (`/admin/agent-config`)
- [x] **4** — experiments CRUD API
- [x] **5** — Reviewer agent + review API stub + reviewer tools
- [ ] **6** — nightly/CI (optional)

**Live today:** full agent-config stack (API, DB migrations `schema_095`–`schema_096`, effective runtime_config, router overlays, delegate kill-switch), Operator + Reviewer tools, tuning WebUI (knobs/sessions/experiments/analysis), benchmark cohort/fingerprint tracking, experiments + review service, failure patterns.

**Optional / not implemented:** Phase 6 nightly/CI webhook jobs (off by default).

---

## Related

| Doc | Role |
|-----|------|
| [`PLANNING.md`](./PLANNING.md) | **Start here** |
| [`implementation-plan.md`](./implementation-plan.md) | Phase checklist + tool IDs |
| [`agent-llm-benchmark.md`](./agent-llm-benchmark.md) | Harness |
