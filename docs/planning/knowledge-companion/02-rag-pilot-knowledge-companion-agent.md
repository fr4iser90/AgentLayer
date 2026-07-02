---
doc_id: knowledge-task-02-rag-pilot
domain: agentlayer_docs
tags: [knowledge-companion, task, rag, agent]
status: done
---

## Task 02 — RAG pilot + knowledge companion

**Status:** done (baseline implementation)  
**Depends on:** [01](./01-docs-and-boundaries.md)  
**Runbook:** [`RUNBOOK-pilot.md`](./RUNBOOK-pilot.md)

### Implemented

- [x] `plugins/agents/knowledge_companion/` (`agent.yaml`, `system_prompt.md`)
- [x] Default `rag_tenant_shared_domains` includes `tenant_knowledge` (new installs / file default)
- [x] Organization Web UI: `/app/org/knowledge` (Tenant Admin surface; pilot uses platform admin role)
- [x] Sample content: `content/healthcare-pilot/beatmungsschlauch-wechsel.md`
- [x] Pilot runbook (Web UI only)

### Manual verification still required

- [ ] Operator embedding stack configured on your deployment
- [ ] Existing DB: patch `rag_tenant_shared_domains` if still `agentlayer_docs` only
- [ ] Ingest + chat smoke per runbook (Admin UI)

### Next tasks

→ [03 — Tenant user onboarding](./03-tenant-user-onboarding.md) · [04 — CMS light](./04-cms-light.md)
