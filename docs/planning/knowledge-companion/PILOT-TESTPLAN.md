---
doc_id: knowledge-companion-pilot-testplan
domain: agentlayer_docs
tags: [planning, knowledge-companion, pilot, testplan, verification]
status: active
---

## Knowledge companion — Pilot test plan (Phase 7)

Structured verification after **Tasks 01–07**. **Most P0 cases run automatically** via
`tests/e2e/test_knowledge_companion_pilot.py`; manual steps below are fallbacks or UI-only checks.
Use this document to sign off the governed team pilot before onboarding a second org or enabling healthcare connectors.

**Related:**

- Operator steps: [`RUNBOOK-pilot.md`](./RUNBOOK-pilot.md)
- Onboarding workflow: [`tenant-onboarding-checklist.md`](./tenant-onboarding-checklist.md)
- Implementation status: [`IMPLEMENTATION-checklist.md`](./IMPLEMENTATION-checklist.md)

---

## 1. Prerequisites

### Environment

| Check | How | Pass |
|-------|-----|------|
| Stack running | `docker compose up --build` (or local API + Postgres) | API on `:8080`, no crash loop |
| Migrations applied | Logs show `schema_111` … `schema_114` | Alembic at head |
| Embedding reachable | Admin → Interfaces → Memory — test/save embedding model | RAG ingest does not 502 |
| `rag_enabled` | Operator settings | on |
| `rag_tenant_shared_domains` | Includes `tenant_knowledge` | `agentlayer_docs,tenant_knowledge` (typical) |
| Docker image | `content/tenant-templates/` baked in | `docker compose up --build` after Task 07 |

### Test accounts (minimum)

Create via **Platform admin → Users** or use `.env.e2e` fixtures.

| Persona | Site role | Membership | Profession role | Purpose |
|---------|-----------|------------|-----------------|---------|
| **Site Admin** | `site_admin` | `tenant_owner` (tenant A) | — | Platform ops, tenant create |
| **Tenant Admin** | `site_user` | `tenant_admin` (tenant A) | optional | Org setup, override publish |
| **Editor** | `site_user` | `tenant_member` | `content_editor` | Draft, submit for review |
| **Reviewer** | `site_user` | `tenant_member` | `content_reviewer` | Approve / reject |
| **Approver** | `site_user` | `tenant_member` | `content_approver` | Publish to production RAG |
| **End user** | `site_user` | `tenant_member` | `anesthesia_nurse` or `end_user` | Chat search only |
| **Other tenant user** | `site_user` | `tenant_member` (tenant B) | any | Isolation negative test |

Assign profession roles: **Organization → Team** (`/app/org/team`).

### Automated pilot (recommended — replaces most manual P0)

Requires running stack (`docker compose up`), `.env` admin credentials, live embedding + RAG enabled.

```bash
# Full E2E suite (includes pilot + IDOR + tenant RAG)
./scripts/run-e2e-journeys.sh

# Knowledge Companion pilot only
pytest tests/e2e/test_knowledge_companion_pilot.py -m e2e -v

# Unit layer (fast, no server)
pytest tests/unit/test_org_identity_roles.py \
       tests/unit/test_tenant_content_cms.py \
       tests/unit/test_tenant_content_workflow.py \
       tests/unit/test_tenant_profession_policy.py \
       tests/unit/test_tenant_templates.py \
       tests/unit/test_tenant_rag_isolation.py -q
```

| Test plan ID | Automated | Where |
|--------------|-----------|-------|
| P01 surfaces | partial | `test_auth_idor_matrix.py` (403 on admin/org for User B) |
| P02 org setup | yes | `test_pilot_org_setup_required_gate` |
| P03 CMS draft/publish | yes | `test_pilot_review_workflow_chain` |
| P04 review workflow | yes | `test_pilot_review_workflow_chain` |
| P05 profession RAG filter | yes | `test_pilot_profession_rag_filter` |
| P06 chat companion | partial | agent not blocked; **citations/disclaimer not asserted** (LLM-dependent) |
| P07 cross-tenant | yes | `test_pilot_cross_tenant_isolation_via_cms` + `test_tenant_rag_isolation.py` |
| P08 templates | yes | `test_pilot_tenant_templates_list` + provision in sandbox fixture |
| P09 healthcare PHI | yes | `test_pilot_healthcare_phi_publish_blocked` |
| P10 IDOR | yes | `test_auth_idor_matrix.py` |

**Still manual:** Playwright UI smoke (`test_frontend_playwright_i18n.py`), chat answer quality, embedding provider UI config.

---

## 2. Test matrix overview

| ID | Area | Mode | Priority |
|----|------|------|----------|
| P01 | Deployment mode + surfaces | both | P0 |
| P02 | Org setup wizard | `multi_tenant` | P0 |
| P03 | CMS draft / publish (legacy path) | both | P1 |
| P04 | Review workflow (draft → published) | `multi_tenant` | P0 |
| P05 | Profession RBAC + RAG filter | `multi_tenant` | P0 |
| P06 | Knowledge companion chat | both | P0 |
| P07 | Cross-tenant isolation | `multi_tenant` | P0 |
| P08 | Tenant template provisioning | `multi_tenant` | P1 |
| P09 | Healthcare guardrails | `healthcare_ops` | P1 |
| P10 | IDOR / auth boundaries | both | P0 |

**P0** = must pass for pilot sign-off. **P1** = strongly recommended.

---

## 3. Detailed test cases

### P01 — Deployment mode and admin surfaces

**Goal:** Site vs org separation; menu matches mode.

| Step | Action | Expected |
|------|--------|----------|
| 1 | Login as Site Admin | User menu shows **Platform admin** |
| 2 | Open `/app/admin` | Loads (operator settings, users, …) |
| 3 | `deployment_mode = multi_tenant` | User menu shows **Organization** for tenant admins |
| 4 | Login as `role=user`, no tenant admin | **No** Platform admin; **No** Organization (or redirect) |
| 5 | `deployment_mode = agent_system` | **No** Organization menu; team knowledge under Platform admin → Memory |

**Pass:** No user without `site_admin` reaches `/v1/admin/operator-settings` or operator-only APIs.

---

### P02 — Organization setup wizard (`multi_tenant`)

**Goal:** First-time tenant admin must complete `/org/setup`.

| Step | Action | Expected |
|------|--------|----------|
| 1 | New tenant + tenant admin user (tenant B) | `GET /auth/me` → `org_setup_required: true` |
| 2 | Navigate to `/org/knowledge` before setup | Redirect to `/org/setup` |
| 3 | Complete wizard: name, `vertical_profile`, disclaimer | Saves |
| 4 | Publish first note **or** “Start with empty knowledge base” | `setup_completed_at` set |
| 5 | Return to `/org/knowledge` | CMS loads |

**Pass:** Cannot publish team knowledge until setup completes (except content editor path per policy).

---

### P03 — CMS basics (Task 04)

**Goal:** Draft vs published; archive removes from search.

| Step | Actor | Action | Expected |
|------|-------|--------|----------|
| 1 | Editor | Create note, **Save draft** | Status `draft`; not in chat RAG |
| 2 | Editor | **Submit for review** (if workflow enabled) or skip to P04 | Status `in_review` or proceed |
| 3 | Approver | Publish (from `approved`) | Status `published`; chunks in `tenant_knowledge` |
| 4 | End user | Chat: question matching note title | Hit cites title + source |
| 5 | Approver | **Archive** published note | Removed from search |

**Pass:** Draft never appears in production `tenant_knowledge` search.

---

### P04 — Review workflow (Task 06) — **P0**

**Goal:** Governed path; editor cannot skip to production.

| Step | Actor | Action | Expected |
|------|-------|--------|----------|
| 1 | Editor | Save draft “OP-Checkliste Pilot” | OK |
| 2 | Editor | **Submit for review** | Status `in_review`; preview in `tenant_knowledge_draft` only |
| 3 | Editor | Try **Publish** button | Hidden or disabled |
| 4 | Editor | Try edit while `in_review` | Blocked (read-only) |
| 5 | Reviewer | Open **Review queue** tab | Note listed |
| 6 | Reviewer | **Send back** with comment “Kürzer formulieren” | Status `draft`; comment visible |
| 7 | Editor | Fix text, submit again | `in_review` |
| 8 | Reviewer | **Approve** | Status `approved` |
| 9 | Approver | **Publish** | Status `published`; RAG ingest |
| 10 | End user | Chat search | Published content visible |

**Negative:**

| Step | Actor | Action | Expected |
|------|-------|--------|----------|
| 11 | Editor | `POST .../publish` (API) on draft | 409 — must be approved |
| 12 | Reviewer | Reject without comment | 400 |

**Pass:** Full chain draft → in_review → approved → published; audit events recorded (`GET .../audit`).

---

### P05 — Profession RBAC (Task 05) — **P0**

**Goal:** Content and RAG respect role/department tags.

**Setup:** Publish note **“OTA-only SOP”** with `target_profession_roles: ["ota"]`.

| Step | Actor | Action | Expected |
|------|-------|--------|----------|
| 1 | User A (`anesthesia_nurse`) | Chat: ask about OTA-only topic | No hit / not cited (filtered) |
| 2 | User B (`ota`) | Same question | Hit from OTA-only note |
| 3 | Editor | Create draft | OK |
| 4 | Editor | Publish (API) | 403 — missing `content.publish` |
| 5 | Approver | Publish after approval | OK |

**Pass:** `filter_rag_hits` behavior matches UI; trainee category limits work if configured.

---

### P06 — Knowledge companion chat (Task 02/03) — **P0**

| Step | Action | Expected |
|------|--------|----------|
| 1 | Open `/app/chat?agent=knowledge_companion` as end user | Agent loads |
| 2 | Ask operational question matching published note | Answer cites **title** and **source** |
| 3 | Ask “How does AgentLayer deployment work?” | Uses `agentlayer_docs` only if explicitly about product (per prompt) |
| 4 | Ask with no matching RAG content | Agent states no hits; no invented procedure |

**Pass:** Grounded answers with disclaimer tone (learning aid).

---

### P07 — Cross-tenant isolation (Task 03) — **P0**

**Setup:** Tenant A has published content; Tenant B empty (or different content).

| Step | Actor | Action | Expected |
|------|-------|--------|----------|
| 1 | User in tenant A | Chat search | Sees tenant A notes |
| 2 | User in tenant B | Same query | Does **not** see tenant A chunks |
| 3 | Tenant A admin | `POST /v1/org/rag/ingest` with tenant B id (API tamper) | 403 / wrong tenant blocked |

**Automated:** `pytest tests/e2e/test_tenant_rag_isolation.py -m e2e`

**Pass:** Zero cross-tenant leakage in chat and API.

---

### P08 — Tenant templates (Task 07) — **P1**

| Step | Action | Expected |
|------|--------|----------|
| 1 | Admin → Users → Create tenant, template `tpl_healthcare_ops` | Tenant created; `vertical_profile=healthcare_ops` |
| 2 | Check `/app/org/team` for new tenant admin | Default departments + roles seeded |
| 3 | Create with `seed_demo_content=true` (sandbox only) | Demo markdown published; **not** copied from other tenants |
| 4 | Chat on new tenant | Demo note searchable; tenant A content invisible |

**Pass:** Template clones config only; live tenants unchanged when JSON template edited.

---

### P09 — Healthcare vertical guardrails — **P1**

Requires `vertical_profile: healthcare_ops` on tenant or content.

| Step | Action | Expected |
|------|--------|----------|
| 1 | Publish note without patient names | OK |
| 2 | Editor tries publish body with “Patient Schmidt …” | 400 PHI guard (healthcare_ops) |
| 3 | Chat: “Patient Müller Allergien?” | Refusal; no patient-specific answer |
| 4 | Chat: generic checklist question | OK from team notes |

**Pass:** No PHI in CMS publish; companion refuses patient-specific queries.

---

### P10 — Auth / IDOR boundaries — **P0**

| Step | Actor | Endpoint / route | Expected |
|------|-------|------------------|----------|
| 1 | `tenant_member` | `GET /v1/admin/tenants` | 403 |
| 2 | `tenant_member` | `PATCH /v1/org/tenant` (admin fields) | 403 |
| 3 | Tenant A admin | Tenant B org routes | 403 |
| 4 | Site user | `/app/admin` | Blocked unless `site_admin` |

**Automated:** `pytest tests/e2e/test_auth_idor_matrix.py -m e2e`

---

## 4. Mode-specific pilot paths

### Path A — `multi_tenant` (recommended for product pilot)

```text
1. Site Admin: RAG settings OK
2. Site Admin: Create tenant from tpl_healthcare_ops (Admin → Users)
3. Site Admin: Create Tenant Admin user (same tenant_id)
4. Tenant Admin: /org/setup → complete wizard
5. Site Admin: Assign profession roles (Editor, Reviewer, Approver, End users)
6. Run P04 (review workflow) + P05 (RBAC) + P06 (chat) + P07 (isolation)
7. Sign off checklist below
```

### Path B — `agent_system` (solo / lab)

```text
1. Instance setup: choose Agent system
2. Site Admin: Platform admin → Memory — publish or CMS under admin tenant-content
3. Site Admin: Create user (role=user)
4. Run P03 + P06 (chat)
5. Optional: publish with ?override=true from setup wizard
```

---

## 5. Sign-off checklist

**Fast path:** green `./scripts/run-e2e-journeys.sh` + unit block above ⇒ mark P0 automated items done.

Copy into your pilot ticket / release notes.

### Platform (P0)

- [ ] Migrations `schema_111`–`schema_114` applied on pilot DB
- [ ] RAG + embedding operational
- [ ] `rag_tenant_shared_domains` includes `tenant_knowledge`
- [ ] P01 surfaces — pass (automated partial + spot-check UI menus)
- [ ] P07 cross-tenant isolation — pass (`test_pilot_cross_tenant_isolation_via_cms`)
- [ ] P10 IDOR — pass (`test_auth_idor_matrix.py`)

### Governed content (P0, `multi_tenant`)

- [ ] P02 org setup wizard — pass (`test_pilot_org_setup_required_gate`)
- [ ] P04 review workflow full chain — pass (`test_pilot_review_workflow_chain`)
- [ ] P05 profession RAG filter — pass (`test_pilot_profession_rag_filter`)
- [ ] P06 knowledge companion — agent reachable (automated); **manual** spot-check citation in chat UI

### Recommended (P1)

- [ ] P08 tenant template create — pass (`test_pilot_tenant_templates_list`)
- [ ] P09 healthcare PHI — pass (`test_pilot_healthcare_phi_publish_blocked`)
- [ ] Version history visible after publish (manual UI or API `GET .../versions`)
- [ ] Reject comment visible to editor (covered in workflow test via API)

### Explicitly out of scope (do not test for Phase 7)

- FHIR / patient context (Task H07)
- Site admin tenant switch banner
- Self-service signup
- Two-person rule configuration UI

---

## 6. Failure triage

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| Chat never cites team notes | `tenant_knowledge` not in shared domains; or content not **published** | Operator settings; complete review workflow |
| 502 on publish | Embedding backend down | Interfaces → embedding provider |
| Editor can publish directly | User has `content_approver` or tenant admin | Check `/org/team` assignment |
| Colleague sees nothing | Wrong `tenant_id`; content not published | Admin → Users; check note status |
| Cross-tenant leak | Critical — stop pilot | Run e2e isolation tests; check `tenant_id` on RAG rows |
| `in_review` stuck | No reviewer assigned | Assign `content_reviewer` role |
| Template tenant has no roles | Template not selected on create | Admin → Users → template dropdown |

---

## 7. Recording results

For each test case, record:

```text
ID: P04
Date: YYYY-MM-DD
Tester:
Environment: docker / staging
Result: PASS | FAIL
Notes: (screenshot, user ids, tenant ids)
```

When all **P0** items pass, mark Phase 7 complete in [`IMPLEMENTATION-checklist.md`](./IMPLEMENTATION-checklist.md) and proceed to second-org onboarding or healthcare connector planning (gated).

---

## 8. Document history

| Date | Change |
|------|--------|
| 2026-07-02 | Initial test plan — Tasks 01–07 baseline, Phase 7 verification |
