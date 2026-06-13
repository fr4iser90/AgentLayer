---
skill_id: orchestrator_workspace
agents: general
---

## Orchestrator: workspace workflow

- For a **different repo** than the current chat project: **`workspace.list`** → **`workspace.create`** (`git_url`, `bind: true`) or **`bind`** **before** **`delegate`**. Sub-agents inherit only the bound workspace.
- After **workspace.create** with `bind: true`, do not call **workspace.list** in a loop — delegate to the specialist next.
