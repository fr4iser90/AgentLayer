---
doc_id: healthcare-task-03-tenant-onboarding
domain: agentlayer_docs
tags: [healthcare, task, tenant, users]
status: done
---

## Task 03 — Tenant user onboarding

**Status:** done  
**Depends on:** [02](./02-rag-pilot-knowledge-companion-agent.md)  
**Goal:** Invite colleagues into the same tenant so they can **search** published
tenant knowledge via `knowledge_companion` — still no Content Editor role yet.

### Scope

- [x] Document tenant user invite flow for pilot (admin creates users via
      `POST /v1/admin/users` with `role=user`, same `tenant_id`).
- [x] Verify `knowledge_companion` is invokable by `role=user` (`min_role: user`).
- [x] Verify RAG search on `tenant_knowledge` works for non-admin users in the
      same tenant (tenant-wide domain).
- [x] Verify tenant isolation: user in `tenant_id=2` cannot retrieve tenant 1 chunks.
- [x] Add minimal audit expectation (log or document): who searched, which domain,
      which document ids returned (logging in `search_for_identity`).
- [x] Optional: link to pilot runbook for chosen vertical profile

### Files likely touched

- `docs/planning/knowledge-companion/03-tenant-user-onboarding.md`
- `docs/security/idor-auth-test-matrix.md` (add tenant_knowledge RAG row if tests added)
- `tests/unit/test_tenant_rag_isolation.py`, `tests/e2e/test_tenant_rag_isolation.py`
- `apps/backend/domain/agent_runtime/governance.py`, `access.py`
- `apps/frontend/src/pages/ChatPage.tsx` (`?agent=knowledge_companion`)

### Out of scope

- SSO / LDAP / HR import
- Profession roles (anesthesia nurse vs OTA)
- Content upload by non-admin users
- Department-based content filtering

### Acceptance criteria

- [x] Admin creates second user in same tenant; user can chat with
      `knowledge_companion` and retrieve shared `tenant_knowledge` hits.
- [x] Second tenant cannot see first tenant's knowledge chunks.
- [x] Non-admin cannot call `POST /v1/admin/rag/ingest` (403/401).
- [x] Pilot runbook explains: admin publishes, users read/search only.

### Manual smoke test

1. Admin ingests content to `tenant_knowledge`.
2. Create `user_b@…` with `role=user`, same tenant.
3. Login as `user_b`, open `/app/chat?agent=knowledge_companion`, ask the same question → same source hit.
4. Create user in different tenant → no cross-tenant hits.

### Exit criteria

- [x] Acceptance criteria met.
- [x] README status updated.

### Next task

→ [04 — CMS light](./04-cms-light.md) or [05 — Profession RBAC](./05-profession-rbac.md) after 04
