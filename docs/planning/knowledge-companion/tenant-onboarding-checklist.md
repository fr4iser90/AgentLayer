---
doc_id: knowledge-companion-tenant-onboarding
domain: agentlayer_docs
tags: [planning, knowledge-companion, tenant, onboarding, templates]
---

## Tenant onboarding checklist

Step-by-step workflow for **Platform Admin** and **Tenant Admin** when bringing a
new organization onto the knowledge companion platform.

**Modes:**

| Phase | How tenants are created |
|-------|-------------------------|
| **Now (pilot)** | Manual setup — treat as prototype for a future template |
| **Target (Task 07)** | `POST /v1/admin/tenants` with `template_id` → customize |

Related:

- Platform plan: [`../knowledge-companion-plan.md`](../knowledge-companion-plan.md)
- Templates (future): [`./07-tenant-templates.md`](./07-tenant-templates.md)
- Vertical profiles: [`./verticals/README.md`](./verticals/README.md)

---

## Admin surfaces (keep separate)

| Surface | Web UI | Who | Typical tasks |
|---------|--------|-----|---------------|
| **Platform admin** | `/app/admin` | Operator, deployment owner | RAG/embedding config, create tenants, global tools/agents |
| **Organization** | `/app/org` | Tenant Admin | Publish team knowledge, invite users (future), departments (Task 05) |

Do **not** put tenant content workflows under Platform → Interfaces. Interfaces is
operator infrastructure only.

Pilot limitation: Task **03b** split platform vs org admin; Task **03** enables
colleague search via `knowledge_companion` in the same tenant.
See [`00-roles-and-scopes.md`](./00-roles-and-scopes.md) and Task **03b** for the target split.

---

## Platform Admin checklist

Use when onboarding a **new organization** (clinic team, field service unit, internal ops).

### 1. Choose vertical profile

| Profile | Template (future) | Use when |
|---------|-------------------|----------|
| `healthcare_ops` | `tpl_healthcare_ops` | clinical teams, hospital departments |
| `default_ops` | `tpl_default_ops` | generic internal ops, IT, logistics |
| `field_service_ops` | `tpl_field_service_ops` | technicians, maintenance (stub) |

See [`verticals/healthcare-ops.md`](./verticals/healthcare-ops.md) for healthcare rules.

### 2. Create live tenant

**Manual (today):**

- [ ] `POST /v1/admin/tenants` — body: `{ "name": "org-slug" }` (see operator API)
- [ ] Or reuse pilot tenant for solo dev only
- [ ] Record `tenant_id` and slug

**From template (Task 07):**

- [ ] `POST /v1/admin/tenants` with `template_id`, `seed_demo_content: false` for production orgs
- [ ] Use `seed_demo_content: true` only for demo/sandbox tenants

### 3. Apply platform config (manual today)

- [ ] Add `tenant_knowledge` to `rag_tenant_shared_domains` (operator settings)
- [ ] Ensure `rag_enabled` is on and embedding stack works
- [ ] Set tenant `vertical_profile` when supported (today: document in runbook until DB field exists)
- [ ] Enable `knowledge_companion` agent for tenant users

### 4. Create first Tenant Admin

- [ ] `POST /v1/admin/users` — `role=admin` or dedicated tenant admin when RBAC lands (task 05)
- [ ] Same `tenant_id` as new tenant
- [ ] Hand off credentials securely; Tenant Admin owns day‑2 ops

### 5. Optional demo content

- [ ] **Production org:** no copied content from other tenants; Tenant Admin writes own Markdown
- [ ] **Demo tenant only:** publish sample files from `content/<vertical>-pilot/` via Admin UI

### 6. Handoff to Tenant Admin

Provide:

- tenant name and id
- chosen `vertical_profile`
- link to this checklist (Tenant Admin section)
- reminder: self-authored content only in Phase 1; no PHI / customer PII unless vertical gates passed

---

## Tenant Admin checklist

Use after Platform Admin created the tenant.

### 1. Organization setup (mandatory wizard — Task 03b)

First login as Tenant Admin → **`/app/org/setup`** (blocks other org pages until done):

- [ ] Confirm tenant name and `vertical_profile`
- [ ] Accept disclaimer / learning-aid policy
- [ ] Publish first note **or** check **“Start with empty knowledge base”**
- [ ] Optional in wizard: first department, first colleague invite

After wizard: define remaining departments, profession templates, qualifications (Task 05).

### 2. Users and roles

- [ ] Invite users: `POST /v1/admin/users` with `role=user`, correct `tenant_id`
- [ ] Assign profession role + department per user (manual metadata until task 05)
- [ ] Assign qualifications with `valid_until` where relevant
- [ ] Identify Content Editor / Reviewer / Approver (may be same person in pilot)

### 3. Content (self-authored)

- [ ] Write Markdown notes: checklists, intervals, onboarding, FAQs
- [ ] Set metadata: author, disclaimer (`learning_aid`), target roles/departments
- [ ] **Do not** upload scans of official SOPs, vendor PDFs, or screenshots with identifiers
- [ ] Healthcare: see [`verticals/healthcare-ops.md`](./verticals/healthcare-ops.md) content rules

### 4. Publish to knowledge base

**Web UI (Task 04 CMS):**

- [ ] **Organization → Knowledge base** (`/app/org/knowledge`) — draft → publish
- [ ] Verify with `knowledge_companion`: question → answer cites your title/source + version

**Legacy direct ingest** (operator API) still available; prefer CMS.

### 5. Pilot smoke test

- [ ] Admin finds ingested content via companion
- [ ] End user in same tenant sees same published content
- [ ] User in **different** tenant does **not** see your content
- [ ] Blocked query patterns work (e.g. patient-specific question with `healthcare_ops`)
- [ ] Answers show disclaimer and source version

### 6. Ongoing operations

- [ ] Edit content → re-publish → RAG re-ingest (replace by `source_uri`)
- [ ] Archive deprecated notes
- [ ] Review audit logs when available
- [ ] Do not enable vertical connectors (FHIR, CRM, …) until vertical task gates pass

---

## Solo pilot shortcut (you, now)

Minimal path before templates and CMS exist:

```text
1. Platform admin: create tenant (Admin → Users) OR use tenant_id=1 for solo pilot
2. Platform admin: rag_tenant_shared_domains includes tenant_knowledge (Admin → Interfaces → Memory)
3. Organization admin: publish 3–5 Markdown notes (/app/org/knowledge)
4. Chat: test knowledge_companion
5. Platform admin: invite 1 colleague as user → repeat test
6. Note every repeated step → future tpl_healthcare_ops fields
```

---

## What goes in a tenant template (Task 07)

When automating, clone **config only**:

- `vertical_profile`
- `rag_tenant_shared_domains` slice
- `knowledge_companion` agent policy
- enabled `knowledge.*` tools
- profession role **templates** (names, not users)
- department **templates**
- workflow defaults (draft → review → publish)
- optional seed Markdown (demo templates only)

Never clone: users, passwords, RAG chunks, another tenant’s content.

---

## Decision guide

| Question | Answer |
|----------|--------|
| New customer org? | **New live tenant** (from template when available) |
| Same team, same hospital? | **Same tenant**, new users |
| Try another industry? | **New tenant** + different `vertical_profile` |
| Show product demo? | **Demo tenant** + sample content, not production |
| Copy content from Tenant A to B? | **No** in production; rewrite or permissioned export only |
