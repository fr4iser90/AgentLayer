---
skill_id: dashboard_layout_proposal_nudge
agents: dashboard
---

**Layout proposals required** — the user asked for layout options/variants.

Your last reply was text-only; that does **not** show preview cards in the chat.

**Next step (mandatory):** call ``propose_layouts`` with **1–3** complete ``ui_layout`` objects (reuse ``data`` paths from ``dashboard.read``). Each proposal: ``title``, ``summary``, ``ui_layout``.

Do **not** describe designs in prose again. After the tool succeeds, give a **short** line pointing to the preview cards.
