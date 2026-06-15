# Benchmark tuning — task index

**Canonical document:** [`agent-tuning-platform.md`](./agent-tuning-platform.md) (English, codebase-verified).

This file is a **checklist index** only. Detailed design, API inventory, and knob catalog live in the linked docs.

## Related docs

| Doc | Role |
|-----|------|
| [`agent-tuning-platform.md`](./agent-tuning-platform.md) | Master plan, APIs, phases |
| [`knob-registry.yaml`](./knob-registry.yaml) | Knob metadata v1 |
| [`pattern-analysis-roadmap.md`](./pattern-analysis-roadmap.md) | Failure pattern taxonomy |
| [`agent-llm-benchmark.md`](./agent-llm-benchmark.md) | Harness, isolation, tiers |
| [`experiments/README.md`](./experiments/README.md) | Human experiment notes |

## Implementation checklist

### Phase 0 — Documentation
- [x] `agent-tuning-platform.md`
- [x] `knob-registry.yaml` v1
- [x] Cross-links in `docs/README.md`
- [ ] ADR `0008-agent-config-experiments.md`

### Phase 1 — Fingerprint + changelog
- [ ] `compute_agent_config_fingerprint()`
- [ ] DB: `agent_config_changelog`, `benchmark_runs.cohort_json`
- [ ] `GET /v1/admin/agent-config/fingerprint`, `/changelog`
- [ ] Fingerprint at benchmark start
- [ ] Admin changelog tab (minimal)

### Phase 2 — Pattern analysis + cohort stats
- [ ] `tests/benchmarks/agent/patterns.py`
- [ ] `GET /v1/admin/benchmarks/analysis`
- [ ] Cohort filters on `/stats`
- [ ] UI cluster + pattern views

### Phase 3 — Knob registry Web UI
- [ ] `GET /v1/admin/agent-config/knobs`
- [ ] Grouped knob browser + operator apply

### Phase 4 — Experiments + auto-run
- [ ] Experiment CRUD + `POST .../experiments/{id}/run`
- [ ] Suite presets (`routing-core`)
- [ ] Harness preset on start run

### Phase 5 — LLM reviewer
- [ ] `POST /v1/admin/benchmarks/review`
- [ ] Admin review tab + human accept

### Phase 6 — CI (optional)
- [ ] Git webhook → routing-core run

**MVP:** Phase 0 + 1 + 2 + 4, then Phase 5.
