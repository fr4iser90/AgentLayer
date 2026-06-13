---
skill_id: dashboard_discipline
agents: dashboard
---

## **Dashboard** discipline

- Use **native tool_calls** only — never paste JSON like ``{"name": "…", "arguments": {…}}`` in assistant text.
- Prefer ``dashboard_id`` from **[Dashboard context]**; call ``dashboard.read`` before layout changes when you need current ``ui_layout`` + ``data``.
- **Security / scan data** is not layout-only: use ``resolve`` + ``list_update`` per row, or ``task_create`` (``assigned_agent_id: general``) for multi-repo sync. Never say security tools are missing.
- For layout **options** or **redesigns**: call ``propose_layouts`` with 1–3 proposals. Each ``ui_layout`` must be ``{version: 1, blocks: [...]}`` (not a bare block array). The user picks via **preview cards in chat** — do **not** ask "1, 2 or 3?" in prose.
- Never paste ``{"name": "propose_layouts", ...}`` in assistant text. No simulated user replies, no ``[Thought]`` / planning monologue in the final message.
- Reuse prior tool JSON in the transcript; do not repeat identical ``read`` calls.
