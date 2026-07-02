---
doc_id: healthcare-task-05-profession-rbac
domain: agentlayer_docs
tags: [healthcare, task, rbac, tenant, profession]
status: pending
---

## Task 05 — Profession RBAC

**Status:** pending  
**Depends on:** [03b](./03b-identity-roles-and-surfaces.md), [04](./04-cms-light.md)  
**Spec:** [Layer 3 in roles model](./00-roles-and-scopes.md#layer-3--profession--content-roles-tenant-local)  
**Goal:** Tenant Admin can define **profession roles**, departments, and
qualifications (generic platform); content and tools filter by effective policy.
Healthcare pilot uses example values (anesthesia nurse, OTA, trainee).

### Scope

#### Identity extensions (generic names)

- [ ] Tables or JSON policy store for:
  - `departments` (tenant-scoped)
  - `profession_roles` (tenant-configurable templates)
  - `user_profession_assignments` (user ↔ profession role ↔ department)
  - `user_qualifications` (type, valid_until, evidence ref)
- [ ] Keep **site role** (`site_admin` / `site_user`) separate from **tenant membership**
      and from profession roles — see [`00-roles-and-scopes.md`](./00-roles-and-scopes.md).

#### Tenant Admin APIs / UI

- [ ] CRUD departments and profession role templates.
- [ ] Assign users to roles and departments.
- [ ] Assign qualifications with expiry.
- [ ] Effective policy preview: "what can this user see/do?"

#### Permission enforcement

- [ ] CMS: Content Editor role can create/edit drafts (not only platform admin).
- [ ] CMS: filter published content retrieval by `target_profession_roles` /
      `target_departments` and optional `required_qualifications`.
- [ ] Tools: map profession roles to allowed capabilities (`knowledge.search`, etc.).
- [ ] Trainee role: limited categories (e.g. onboarding only).

#### Agent behavior

- [ ] `knowledge_companion` receives compact context capsule: active profession role,
      department, qualification summary (not a prompt dump).
- [ ] Apply `vertical_profile` rules (e.g. `healthcare_ops` PHI deny) on top of RBAC.
- [ ] Deny or narrow answer when content requires qualification user lacks.

### Files likely touched

- `apps/backend/domain/identity/`
- New `apps/backend/domain/tenant_knowledge/` or extend tenant policy modules
- Admin API controllers + frontend admin pages
- `apps/backend/domain/plugin_system/tool_policy.py` (profession context hooks)
- Tests: role filter, qualification expiry, deny-by-default

### Out of scope

- HR/LDAP/SSO claim import (document as future)
- Patient-context ABAC (healthcare vertical, task 07)
- FHIR

### Acceptance criteria

- [ ] Tenant Admin assigns User A = anesthesia nurse, OR dept; User B = trainee.
- [ ] Published content tagged "OTA only" not returned to User A (or clearly scoped).
- [ ] Expired qualification blocks qualification-gated content.
- [ ] Content Editor (non-platform-admin) can save drafts but not publish (until task 06).

### Exit criteria

- [ ] Acceptance criteria met.
- [ ] ADR candidate: tenant profession authorization model.

### Next task

→ [06 — Review and approval workflow](./06-review-approval-workflow.md)
