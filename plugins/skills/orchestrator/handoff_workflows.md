---
skill_id: orchestrator_handoffs
agents: general
---

## Orchestrator: multi-agent handoffs

- **Multi-step handoff:** when a sub-agent response includes `artifact_id`, the next step is **one** **`delegate`** to **coding** with `artifact_refs`, `requirements` including `mode: fix_from_artifact` and `branch: <name>` when requested.
- **Security → fix flow:** `security_auditor` scan → artifact → **`delegate`** `coding` with `artifact_refs`.
- **Dashboard + scan fields:** delegate `security_auditor` first, then `dashboard` to `list_update` board rows.
