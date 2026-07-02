---
doc_id: knowledge-task-02-rag-pilot
domain: agentlayer_docs
tags: [knowledge-companion, task, rag, agent]
status: pending
---

## Task 02 — RAG pilot + knowledge companion

**Status:** pending  
**Depends on:** [01](./01-docs-and-boundaries.md)  
**Goal:** Ship a **generic** solo pilot: self-authored Markdown in `tenant_knowledge`,
searchable via `knowledge_companion` — **any industry**, optional vertical profile.

### Scope

#### A. RAG domain (generic)

- [ ] Add `tenant_knowledge` to `rag_tenant_shared_domains`.
- [ ] Ingest with `domain: "tenant_knowledge"`, scoped to tenant.
- [ ] Optional sample content: `content/pilot/` or `content/healthcare-pilot/` if
      using `healthcare_ops` profile.

#### B. `knowledge_companion` agent (generic)

- [ ] `plugins/agents/knowledge_companion/agent.yaml` + `system_prompt.md`
- [ ] `min_role: user`
- [ ] Tool policy: `rag_search` / `rag` domain
- [ ] Optional `vertical_profile` in config:
  - `default_ops` — generic team knowledge, no PHI rules
  - `healthcare_ops` — add PHI refusal + clinical disclaimer (see
    [healthcare-ops](../verticals/healthcare-ops.md))
- [ ] System prompt (platform): cite sources, disclaimer, refuse when no published hit
- [ ] Default RAG domain: `tenant_knowledge` (not `agentlayer_docs`)

#### C. Interim admin ingest

- [ ] Document `POST /v1/admin/rag/ingest` with `domain: "tenant_knowledge"`

### Out of scope

- CMS, profession RBAC, vertical connectors (FHIR, CRM, …)

### Acceptance criteria

- [ ] Admin ingests self-authored content → `tenant_knowledge`
- [ ] User can query via `knowledge_companion` with citations
- [ ] `agentlayer_docs` not mixed into default answers
- [ ] If `healthcare_ops` enabled: patient-specific queries refused

### Next tasks

→ [03](./03-tenant-user-onboarding.md) · [04](./04-cms-light.md)
