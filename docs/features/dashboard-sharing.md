---
doc_id: feature-dashboard-sharing
domain: agentlayer_docs
tags: [dashboards, sharing, aggregation]
---

# Dashboard sharing & aggregation

Dashboard sharing is **separate** from [friend share grants](shares.md) (`google_calendar`, etc.).

## Three sharing mechanisms

| Mechanism | Who | What you see |
|-----------|-----|--------------|
| **Membership** | Users in the **same tenant** | Full board with role `viewer` / `editor` / `co_owner` |
| **Block grant** | Users in the tenant | That board in **your sidebar list** — only selected `block_ids` (+ filtered `data`) |
| **Public link** | Anyone with token | Read-only at `/app/dashboard/shared?t=…` — **not** in the sidebar |

Shared boards appear as **their own list entry**, not embedded inside Personal unless you add a **`dashboard_ref`** block (live) or **import/copy** layout (snapshot).

## Live refs & pins

- Block type **`dashboard_ref`**: read-only mirror of one block from another dashboard you can access.
- **Pin**: `POST /v1/dashboards/{id}/pin-block` adds a `dashboard_ref` on a board you can edit.
- API: `GET /v1/dashboards/{source_id}/blocks/{block_id}/render`

## Template copy (no live sync)

- Export: `GET /v1/dashboards/{id}/export-template`
- Import: `POST /v1/dashboards/from-template`
- Agent: `import_layout`, `export_template`

## Agent recipe — copy block layout

1. `dashboard.read` on source board (note `block_ids`, `ui_layout`, `data` paths).
2. On target board: `patch_layout` with `add_block` ops (matching types/props).
3. `patch_data` for the `dataPath` keys used by those blocks.

For a live view instead, use `pin-block` or `add_block` type `dashboard_ref` with `source_dashboard_id` + `source_block_id`.

## Multiple dashboards

You can have **unlimited** boards (`custom`, templates, shared). Personal / inbox aggregation is **optional** — one overview among many.
