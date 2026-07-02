---
doc_id: healthcare-task-04-cms-light
domain: agentlayer_docs
tags: [healthcare, task, cms, rag, tenant-content]
status: pending
---

## Task 04 — CMS light (`tenant_content` + publish → RAG)

**Status:** pending  
**Depends on:** [02](./02-rag-pilot-knowledge-companion-agent.md)  
**Goal:** Replace manual curl ingest with a **generic minimal CMS**: store Markdown +
metadata in `tenant_content`, publish triggers RAG ingest into `tenant_knowledge`.

### Scope

#### Data model (minimum, generic)

- [ ] Table(s) for tenant content, e.g. `tenant_content`:
  - `id`, `tenant_id`, `slug`, `title`, `body_md`
  - `status`: `draft` | `published` | `archived`
  - `source_type`: `self_authored` (MVP default)
  - `disclaimer_level`: `learning_aid` | `local_draft` | `approved`
  - `target_profession_roles`, `target_departments` (JSON arrays; filter in task 05)
  - `vertical_profile` optional tag (e.g. `healthcare_ops`)
  - `author_user_id`, `published_at`, `version`, `content_sha256`
  - audit timestamps
- [ ] Migration under `apps/backend/infrastructure/db/migrations/`.

#### API

- [ ] Admin (or future Content Editor) CRUD:
  - `GET/POST /v1/admin/tenant-content`
  - `GET/PATCH /v1/admin/tenant-content/{id}`
  - `POST /v1/admin/tenant-content/{id}/publish`
  - `POST /v1/admin/tenant-content/{id}/archive`
- [ ] Runtime read (published only):
  - `GET /v1/tenant-content/{slug}` or search endpoint for agent tools.

#### Publish → RAG

- [ ] On publish: call existing ingest path with:
  - `domain: tenant_knowledge`
  - `source_uri: tenant-content/{id}` or slug
  - replace prior chunks for same `source_uri`
- [ ] On archive: purge RAG rows for that document.
- [ ] Draft content never ingested to production domain.

#### Validation (MVP)

- [ ] Reject empty body.
- [ ] Optional heuristic: flag obvious patient identifier patterns (healthcare profile).
- [ ] Require `source_type=self_authored` unless explicit override flag for admins.

#### Agent / tools

- [ ] Optional tool `knowledge.search` wrapping published content + RAG.
- [ ] Or keep `rag_search(domain=tenant_knowledge)` as primary read path.

### Files likely touched

- `apps/backend/infrastructure/db/migrations/versions/schema_*_tenant_content.py`
- `apps/backend/domain/` (tenant content module)
- `apps/backend/api/` tenant content router
- `apps/backend/infrastructure/rag/rag_core.py` (publish hook)
- `plugins/agents/knowledge_companion/` (cite CMS version metadata)
- Optional: minimal admin UI page

### Out of scope

- Reviewer / Approver multi-step workflow (task 06)
- Profession-based retrieval filters (task 05)
- File upload / PDF ingest
- Version diff UI
- Multilingual workflow

### Acceptance criteria

- [ ] Admin creates draft Markdown note in CMS UI or API.
- [ ] Draft is not returned by `rag_search` / knowledge companion.
- [ ] Publish ingests to `tenant_knowledge`; companion answers with title + version.
- [ ] Edit + re-publish replaces old chunks (same `source_uri`).
- [ ] Archive removes content from search.

### Manual smoke test

1. Create draft "OP-Vorbereitung Checkliste".
2. Confirm RAG miss while draft.
3. Publish → companion finds checklist.
4. Edit body, publish again → answer reflects new version.
5. Archive → companion no longer cites it.

### Exit criteria

- [ ] Acceptance criteria met.
- [ ] Consider ADR: tenant content publication model.

### Next task

→ [05 — Profession RBAC](./05-profession-rbac.md)
