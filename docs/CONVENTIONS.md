---
doc_id: docs-conventions
domain: agentlayer_docs
---

## Documentation conventions (AgentLayer)

This file is optional in other workspaces; scheduled **doc maintenance** reads it when present.

### Layout

- **Index:** `docs/README.md` — start here for humans and RAG.
- **Decisions:** `docs/adr/` — one ADR per architectural choice.
- **Features / architecture / runbooks:** under `docs/features/`, `docs/architecture/`, `docs/runbooks/`.
- **Per-run agent log:** `docs/MAINTENANCE_REPORT.md` (scheduler append).
- **Project memory (agent):** `docs/DOC_PROFILE.md` — inventory, doc roots, gaps (updated by doc maintenance).

### Style

- English for product docs unless a page is explicitly localized.
- Short sections with stable `##` headings; include file paths and endpoint paths where relevant.
- Prefer fixing broken links over adding new orphan pages.

### Modes (scheduler)

- **`respect`** (default): follow this repo’s layout; small fixes only.
- **`bootstrap`**: may create minimal `docs/README.md`, `docs/CONVENTIONS.md`, `docs/DOC_PROFILE.md` only when missing (see preset `doc_maintenance_bootstrap_30m`).
