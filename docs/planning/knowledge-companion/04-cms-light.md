---
doc_id: healthcare-task-04-cms-light
domain: agentlayer_docs
tags: [healthcare, task, cms, rag, tenant-content]
status: done
---

## Task 04 — CMS light (`tenant_content` + publish → RAG)

**Status:** done  
**Depends on:** [02](./02-rag-pilot-knowledge-companion-agent.md)  
**Goal:** Replace manual curl ingest with a **generic minimal CMS**: store Markdown +
metadata in `tenant_content`, publish triggers RAG ingest into `tenant_knowledge`.

### Scope

#### Data model (minimum, generic)

- [x] Table `tenant_content` (migration `schema_112`)
- [x] Fields: id, tenant_id, slug, title, body_md, status, source_type, disclaimer_level,
      target arrays, vertical_profile, author, published_at, version, content_sha256, timestamps

#### API

- [x] Org + site admin CRUD: `/v1/org/tenant-content`, `/v1/admin/tenant-content`
- [x] Publish / archive actions
- [x] Runtime read: `GET /v1/tenant-content/{slug}` (published, same tenant)

#### Publish → RAG

- [x] Publish → `tenant_knowledge` with `source_uri: tenant-content/{id}`
- [x] Archive → purge RAG rows for source_uri
- [x] Draft never ingested; editing published body demotes to draft + purges RAG

#### Validation (MVP)

- [x] Reject empty body
- [x] PHI heuristic on publish for `healthcare_ops`
- [x] `source_type=self_authored` only

#### UI

- [x] Org CMS at `/app/org/knowledge` (`OrgContentCms`)
- [x] Agent system CMS under Platform admin → Memory

### Acceptance criteria

- [x] Admin creates draft Markdown note in CMS UI or API
- [x] Draft is not returned by `rag_search` / knowledge companion
- [x] Publish ingests to `tenant_knowledge`; companion answers with title + version
- [x] Edit + re-publish replaces old chunks (same `source_uri`)
- [x] Archive removes content from search

### Next task

→ [05 — Profession RBAC](./05-profession-rbac.md)
