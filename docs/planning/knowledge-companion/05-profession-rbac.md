---
doc_id: healthcare-task-05-profession-rbac
domain: agentlayer_docs
tags: [healthcare, task, rbac, tenant, profession]
status: done
---

## Task 05 — Profession RBAC

**Status:** done (baseline)  
**Depends on:** [03b](./03b-identity-roles-and-surfaces.md), [04](./04-cms-light.md)  
**Spec:** [Layer 3 in roles model](./00-roles-and-scopes.md#layer-3--profession--content-roles-tenant-local)  
**Goal:** Tenant Admin can define **profession roles**, departments, and
qualifications (generic platform); content and tools filter by effective policy.

### Scope

#### Identity extensions (generic names)

- [x] Tables: `tenant_departments`, `tenant_profession_roles`, `user_profession_assignments`, `user_qualifications`
- [x] `tenant_content.required_qualifications`, `content_category`
- [x] Site / tenant membership / profession layers kept separate

#### Tenant Admin APIs / UI

- [x] CRUD departments and profession role templates (seed defaults on first use)
- [x] Assign users to roles and departments
- [x] Assign qualifications with expiry
- [x] Effective policy preview: `GET /v1/org/me/profession-policy`

#### Permission enforcement

- [x] CMS: `content_editor` can create/edit drafts (not publish alone)
- [x] CMS: `content_approver` / tenant admin can publish
- [x] CMS: **write scope** — when a profession role sets `content_categories`,
  edit/review/publish is limited to notes with that `content_category`
  (plus department match when the note has `target_departments` and the user
  has a department). Empty categories = unrestricted editor/reviewer.
  Tenant admin / `profession.admin` bypasses scope.
- [x] RAG: filter `tenant_knowledge` hits by profession/department/qualification/category
- [x] Trainee: limited to `content_category` in role template

#### Agent behavior

- [x] `knowledge_companion` receives compact profession context capsule in system prompt
- [x] Vertical PHI rules unchanged (`healthcare_ops`)

### Acceptance criteria

- [x] Tenant Admin assigns User A = anesthesia nurse, User B = trainee (via Team UI + API)
- [x] Published content tagged `ota` not returned to anesthesia nurse in RAG filter
- [x] Expired qualification blocks qualification-gated content
- [x] Content Editor can save drafts but not publish (until approver role)

### Next task

→ [06 — Review and approval workflow](./06-review-approval-workflow.md)
