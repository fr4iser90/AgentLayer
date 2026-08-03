---
doc_id: knowledge-companion-implementation-checklist
domain: agentlayer_docs
tags: [planning, knowledge-companion, checklist, implementation]
---

## Implementation checklist — roles, modes, surfaces

Master checklist for everything agreed in planning. Spec:
[`00-roles-and-scopes.md`](./00-roles-and-scopes.md).

**Legend:** `[x]` done · `[ ]` open · `[~]` partial

---

### Phase 0 — Documentation (done)

- [x] Generic knowledge companion plan
- [x] Roles model: site / tenant / profession layers
- [x] Deployment mode: `agent_system` vs `multi_tenant`
- [x] UI split: `/admin` vs `/org`
- [x] Decisions: `site_role` column, tenant switch, mandatory `/org/setup`, setup step 3 choice
- [x] Task 03b spec
- [x] This checklist

---

### Phase 1 — Database

- [x] Migration `schema_111_identity_roles_deployment_mode.py`
- [x] `operator_settings.deployment_mode` (`agent_system` | `multi_tenant`, default `multi_tenant`)
- [x] `users.site_role` (`site_admin` | `site_user`), backfill from `users.role`
- [x] `tenant_memberships(user_id, tenant_id, membership_role)` — `tenant_owner` | `tenant_admin` | `tenant_member`
- [x] `tenants.setup_completed_at` (nullable timestamptz)
- [x] `tenants.vertical_profile` (nullable varchar)
- [x] Backfill: existing admins → `site_admin` + `tenant_owner` on their tenant
- [ ] Apply migration on live / dev DB (`alembic upgrade head`)

---

### Phase 2 — Backend auth & API

- [x] `require_site_admin()` — `/v1/admin/*`, operator-settings
- [x] `require_tenant_admin()` — tenant membership admin/owner, same tenant
- [x] `GET /auth/me` — `site_role`, `membership_role`, `deployment_mode`, `org_setup_required`
- [x] `POST /v1/org/rag/ingest` — tenant_admin, domain `tenant_knowledge` only
- [x] `GET /v1/org/tenant` — current tenant profile + setup status
- [x] `PATCH /v1/org/tenant` — org name, vertical_profile (setup)
- [x] `POST /v1/org/setup/complete` — disclaimer, empty-or-publish flag, set `setup_completed_at`
- [x] `POST /auth/setup/deployment-mode` — set mode during instance setup (before admin exists)
- [x] Unit tests: deployment mode setup guard
- [~] IDOR tests: tenant B cannot ingest into tenant A; tenant_member cannot hit org admin routes

---

### Phase 3 — Instance setup wizard (`/app/setup`)

- [x] Step 0: choose **Agent system** vs **Multi-tenant system**
- [x] Persist `deployment_mode` before admin + LLM steps
- [x] Copy/i18n DE + EN

---

### Phase 4 — Organization UI (`multi_tenant` only)

- [x] `RequireOrgAdmin` — tenant_admin/owner (site_admin with membership OK)
- [x] Hide `/org` routes + menu when `deployment_mode = agent_system`
- [x] Mandatory `/org/setup` wizard — blocks `/org/knowledge` until complete
  - [x] Org name + vertical_profile
  - [x] Disclaimer acceptance
  - [x] Publish first note **or** “Start with empty knowledge base”
- [x] `/org/knowledge` → `POST /v1/org/rag/ingest` (not admin route)
- [x] User menu: Organization (tenant) vs Platform admin (site) — conditional

---

### Phase 5 — Agent system mode UI

- [x] Team knowledge under **Platform admin → Memory** (existing section for `agent_system`)
- [x] No Organization menu entry in `agent_system`
- [x] Site admin invites users (admin/users) — no tenant CRUD UI

---

### Phase 6 — Already done (Task 02 baseline)

- [x] `knowledge_companion` agent plugin
- [x] Default `rag_tenant_shared_domains` includes `tenant_knowledge`
- [x] Sample content for private verticals: operator-local only
- [x] Org knowledge publish UI component wired to org API

---

### Phase 7 — Verification

Sign-off: [`PILOT-TESTPLAN.md`](./PILOT-TESTPLAN.md) — automated via `tests/e2e/test_knowledge_companion_pilot.py`

- [ ] `agent_system`: setup → admin publishes team knowledge → user searches in chat (Path B; partial E2E)
- [ ] `multi_tenant`: setup → review workflow → publish → user search (Path A; **E2E automated**)
- [x] Cross-tenant RAG isolation (Task 03 — unit + e2e tests)
- [x] Same-tenant user search (Task 03)
- [x] RUNBOOK + README updated for 03b baseline

---

### Deferred (later tasks)

- [x] Task 04 — CMS `tenant_content` (draft/publish/archive → RAG)
- [x] Task 05 — Profession RBAC (departments, roles, assignments, RAG filter)
- [x] Task 06 — Review workflow (draft → in_review → approved → published)
- [x] Task 07 — Tenant templates (`content/tenant-templates/`, Admin UI)
- [ ] Site admin tenant switch banner in `/admin`

---

### File touch list (implementation)

| Area | Files |
|------|-------|
| Migration | `schema_111_identity_roles_deployment_mode.py` |
| Identity | `identity_tenants.py`, `auth.py`, `request_auth.py` |
| Operator | `operator_settings_*.py` |
| Org API | `api/org/controllers/org_api.py`, `main.py` |
| Setup | `auth_api.py`, `domain/setup/instance.py` |
| Frontend | `SetupWizardPage.tsx`, `RequireSiteAdmin.tsx`, `RequireOrgAdmin.tsx`, `OrgSetupPage.tsx`, `UserMenu.tsx`, `App.tsx` |
| Tests | `tests/unit/test_org_identity_roles.py`, `tests/e2e/test_auth_idor_matrix.py` |
