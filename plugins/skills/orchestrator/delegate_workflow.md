---
skill_id: orchestrator_delegate
agents: general
---

## Orchestrator: delegate workflow

- Answer directly when no specialist is needed (simple chat, greetings, general knowledge one-liners not in the routing table).
- For **calculations and numeric work** (including simple arithmetic): **`delegate`** to **`math`** via native tool_call — do not compute in prose.
- For **any other domain task** in the routing table: **`delegate`** once with a full prompt via **native tool_call** — never describe or paste a delegate call in message text.
- When asked to list agents or route work: invoke **`catalog`** (or **`delegate`** with `list_agents: true`) via **native tool calling** — never write tool names in backticks or paste delegate JSON in the message body.
- When calling tools, **always send required JSON fields**. Empty `{}` calls fail.
- Prefer **one well-chosen delegate** over many discovery rounds. Do not loop on tools without a user-facing summary.
- In delegate **prompts**, use **repo-relative paths** (e.g. `README.md`) — never container paths like `/data/project_workspaces/...`.
- For **read file** tasks: **one** delegate to **`coding_plan`**; do not switch to **`coding`** unless edits or bash are required.
- When **`delegate`** returns **`ok: true`**, reply using **`assistant_excerpt`** only — never invent file contents from general knowledge.
- When **`delegate`** returns **`ok: false`**, retry once with a simpler prompt or tell the user the specialist could not read the repo — **do not guess**.
- For **security scans and remediation**: **`delegate`** to **`security_auditor`** (start → status / deferred_wait → findings) — never route through **`coding_plan`** or **`task`**.
