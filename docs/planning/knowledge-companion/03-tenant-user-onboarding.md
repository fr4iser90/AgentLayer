---
doc_id: healthcare-task-03-tenant-onboarding
domain: agentlayer_docs
tags: [healthcare, task, tenant, users]
status: pending
---

## Task 03 — Tenant user onboarding

**Status:** pending  
**Depends on:** [02](./02-rag-pilot-knowledge-companion-agent.md)  
**Goal:** Invite colleagues into the same tenant so they can **search** published
tenant knowledge via `knowledge_companion` — still no Content Editor role yet.

### Scope

- [ ] Document tenant user invite flow for pilot (admin creates users via
      `POST /v1/admin/users` with `role=user`, same `tenant_id`).
- [ ] Verify `knowledge_companion` is invokable by `role=user` (`min_role: user`).
- [ ] Verify RAG search on `tenant_knowledge` works for non-admin users in the
      same tenant (tenant-wide domain).
- [ ] Verify tenant isolation: user in `tenant_id=2` cannot retrieve tenant 1 chunks.
- [ ] Add minimal audit expectation (log or document): who searched, which domain,
      which document ids returned (implementation may be logging-only in this task).
- [ ] Optional: link to pilot runbook for chosen vertical profile

### Files likely touched

- `docs/planning/knowledge-companion/03-tenant-user-onboarding.md`
- `docs/security/idor-auth-test-matrix.md` (add tenant_knowledge RAG row if tests added)
- `tests/unit/` or `tests/e2e/` for tenant RAG isolation (recommended)
- `apps/frontend/src/pages/admin/` (optional UX only)

### Out of scope

- SSO / LDAP / HR import
- Profession roles (anesthesia nurse vs OTA)
- Content upload by non-admin users
- Department-based content filtering

### Acceptance criteria

- [ ] Admin creates second user in same tenant; user can chat with
      `knowledge_companion` and retrieve shared `tenant_knowledge` hits.
- [ ] Second tenant cannot see first tenant's knowledge chunks.
- [ ] Non-admin cannot call `POST /v1/admin/rag/ingest` (403/401).
- [ ] Pilot runbook explains: admin publishes, users read/search only.

### Manual smoke test

1. Admin ingests content to `tenant_knowledge`.
2. Create `user_b@…` with `role=user`, same tenant.
3. Login as `user_b`, ask knowledge companion the same question → same source hit.
4. Create user in different tenant → no cross-tenant hits.

### Exit criteria

- [ ] Acceptance criteria met.
- [ ] README status updated.

### Next task

→ [04 — CMS light](./04-cms-light.md) or [05 — Profession RBAC](./05-profession-rbac.md) after 04
