# Benchmark experiments (human notes)

Optional directory for **human-written experiment notes** that complement the Admin experiment workflow (planned — see [`agent-tuning-platform.md`](./agent-tuning-platform.md)).

## Convention

One file per experiment cohort:

```text
experiments/
  2026-06-15-routing-v3-catalog-pin.md
  2026-06-20-delegate-router-tweak.md
```

Each file should include:

- **Hypothesis** — what knob(s) you changed and why
- **Git SHA** — commit that introduced the change
- **Cohort label** — matches `cohort_label` on benchmark runs (when implemented)
- **Suite preset** — e.g. `routing-core` or `full`
- **Model matrix** — which profiles were in the run
- **Result summary** — link to Admin run id or `benchmarks/results/{run_id}/`
- **Decision** — accepted / reverted / iterate

Automated changelog and fingerprint data will live in the database once Phase 1 ships; these files are for narrative context and PR descriptions.
