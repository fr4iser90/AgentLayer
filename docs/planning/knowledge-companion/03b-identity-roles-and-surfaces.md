---
doc_id: knowledge-task-03b-identity-roles
domain: agentlayer_docs
tags: [knowledge-companion, task, identity, rbac, tenant, site-admin]
status: done
---

## Task 03b — Identity roles and admin surfaces

**Status:** done (baseline — migration + guards + UI; tenant switch deferred)  
**Depends on:** [03](./03-tenant-user-onboarding.md)  
**Blocks:** clean [05 — Profession RBAC](./05-profession-rbac.md)  
**Spec:** [`00-roles-and-scopes.md`](./00-roles-and-scopes.md)

**Goal:** Split **Site Admin** (deployment) from **Tenant Admin** (organization) in
auth, API, and UI — so `/app/org` works without `/app/admin`.

### Scope

#### Data model

- [ ] `operator_settings.deployment_mode`: `agent_system` | `multi_tenant` (set in `/setup`, Task 03b)
- [ ] `tenant_memberships` table: `user_id`, `tenant_id`, `membership_role`
  (`tenant_owner` | `tenant_admin` | `tenant_member`)
- [ ] `users.site_role` (`site_admin` | `site_user`) — **add column**; keep `users.role` as
      migration alias until deprecated (see [`00-roles-and-scopes.md`](./00-roles-and-scopes.md))
- [ ] `tenants.setup_completed_at` (nullable) — set when mandatory wizard finishes
- [ ] Backfill: existing `users.role=admin` → `site_admin`; first user per tenant
      also gets `tenant_owner` membership (or explicit bootstrap script)

#### Authorization

- [ ] `/app/admin/*` → requires `site_admin`
- [ ] `/app/org/*` → requires `tenant_admin` or `tenant_owner` (same tenant)
- [ ] `POST /v1/admin/rag/ingest` for `domain=tenant_knowledge`:
      allow tenant_admin scoped to own tenant (new route or scoped check)
- [ ] Platform routes (`operator-settings`, tenant create, embedding) → `site_admin` only
- [ ] Site Admin **tenant switch** in `/admin` (banner + audit log) — not user impersonation
- [ ] Tenant APIs under `/v1/org/*` where new routes are added

#### UI

- [ ] `/app/setup` step 0: choose **Agent system** vs **Multi-tenant system**
- [ ] If `agent_system`: hide `/org`, User menu “Organization”; keep team knowledge under **Platform admin**
- [ ] If `multi_tenant`: show `/org`; User menu split as planned
- [ ] User menu: show **Organization** for tenant_admin+ (multi_tenant only); **Platform admin** for site_admin
- [ ] **`/org/setup` mandatory wizard** on first Tenant Admin login — block `/org/knowledge`
      and invites until `setup_completed_at` is set; step 3: publish first note **or**
      explicit “start empty” checkbox (one required)
- [ ] Admin → Users: distinguish site role vs tenant membership role columns

#### Docs

- [ ] Update runbook, onboarding checklist, idor matrix
- [ ] Mark pilot “dual hat” pattern explicitly

### Out of scope

- Profession / content roles (Task 05)
- CMS (Task 04) — may stub publish through existing ingest until CMS lands
- SSO / LDAP
- Multi-tenant membership per user (schema ready, UI single-tenant)

### Acceptance criteria

- [ ] Tenant Admin (`site_user` + `tenant_admin`) must complete `/org/setup` before publish
- [ ] Same user gets 403 on `/app/admin` and operator-settings API
- [ ] Site Admin can still provision tenants and operator settings
- [ ] Tenant member can chat + RAG search but not publish
- [ ] IDOR tests: tenant A admin cannot ingest into tenant B

### Next tasks

→ [04 — CMS light](./04-cms-light.md) · [05 — Profession RBAC](./05-profession-rbac.md)
