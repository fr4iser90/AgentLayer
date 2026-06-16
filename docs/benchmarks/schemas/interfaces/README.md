# Knob value schemas (planning)

JSON Schemas for **values** stored via API (DB / run body) — **not** for `.env` editing.

| File | Used by |
|------|---------|
| [`runtime-config-values.json`](./runtime-config-values.json) | `layer: runtime_config` — routing, limits, forward flags → **agent-config/apply → DB** |
| [`agent-yaml-fields.json`](./agent-yaml-fields.json) | prompts, pinned_tools → **agent-config/apply → DB overlay** |
| [`router-overlay.json`](./router-overlay.json) | router phrase maps → **agent-config/apply → DB overlay** |
| [`bench-harness.json`](./bench-harness.json) | per-run harness opts → **benchmarks/runs** |
| [`operator-tuning-fields.json`](./operator-tuning-fields.json) | operator_settings subset → **operator-settings** |
| [`read-only-fingerprint.json`](./read-only-fingerprint.json) | code/rubric — hash only |

**Removed:** `env-knobs.json` — misleading name; tuning never goes through env.

`bootstrap_env_key` in registry = install default only (see [`../../knob-registry.yaml`](../../knob-registry.yaml) header).
