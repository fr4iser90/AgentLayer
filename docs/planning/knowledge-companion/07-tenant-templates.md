---
doc_id: knowledge-task-07-tenant-templates
domain: agentlayer_docs
tags: [knowledge-companion, task, tenant, templates]
status: pending
---

## Task 07 (platform) — Tenant templates

**Status:** pending  
**Depends on:** [06 — Review and approval workflow](./06-review-approval-workflow.md)  
**Goal:** Platform Admin can create a **new live tenant from a template** instead
of hand-configuring every org.

### Scope

- [ ] `tenant_templates` store (JSON file or DB table)
- [ ] Seed templates: `tpl_default_ops`, `tpl_healthcare_ops`
- [ ] Optional demo tenants: `demo_healthcare`, `demo_default` (synthetic content)
- [ ] API: `POST /v1/admin/tenants` accepts `template_id`, `seed_demo_content`
- [ ] Clone on create: `vertical_profile`, RAG domain allowlist, agent policy,
      profession role templates, workflow defaults — **not** RAG chunks or users
- [ ] Admin UI: "Create tenant from template"
- [ ] Document template authoring for Platform Admin

### Out of scope

- Self-service signup without Platform Admin
- Cross-tenant template editing by Tenant Admin
- Copying production content between tenants

### Acceptance criteria

- [ ] New tenant from `tpl_healthcare_ops` has `vertical_profile` and empty
      `tenant_knowledge` (unless `seed_demo_content=true` for demo only).
- [ ] Tenant B created from template cannot see Tenant A RAG data.
- [ ] Template update does not retroactively change existing live tenants.

### Related

- Plan: [`../knowledge-companion-plan.md`](../knowledge-companion-plan.md) —
  *Tenant Provisioning And Templates*
