---
doc_id: knowledge-companion-runbook-pilot
domain: agentlayer_docs
tags: [planning, knowledge-companion, runbook]
---

## Knowledge companion — pilot runbook

Quick steps after Task 02 implementation. Full checklist:
[`tenant-onboarding-checklist.md`](./tenant-onboarding-checklist.md).

Two admin surfaces — do not mix them:

| Surface | Route | Who | Purpose |
|---------|-------|-----|---------|
| **Platform admin** | `/app/admin` | Operator / you | RAG on/off, embedding, `rag_tenant_shared_domains`, tenants bootstrap |
| **Organization** | `/app/org` | Tenant Admin | Publish team notes → `tenant_knowledge` |

Pilot note: Task **03b** is implemented — platform admin uses `site_role=site_admin`; organization uses `tenant_memberships` (`tenant_owner` / `tenant_admin`). Regular users cannot access `/v1/admin/*` or `/v1/org/*`.
Full model: [`00-roles-and-scopes.md`](./00-roles-and-scopes.md).

### 1. Platform operator settings

User menu → **Platform admin** → **Interfaces → Memory & RAG** → Save:

- `rag_enabled`: on
- `rag_tenant_shared_domains`: `agentlayer_docs,tenant_knowledge`
- Embedding provider + model configured and saved

### 2. Tenant setup (first Tenant Admin login — Task 03b)

**Organization → `/app/org/setup`** (mandatory wizard — blocks other `/org` pages until done):

1. Confirm org name and `vertical_profile`
2. Accept disclaimer / learning-aid policy
3. **Either** publish first note **or** check **“Start with empty knowledge base”** (one required)
4. Optionally: department + first colleague invite

### 3. Publish sample content (after setup)

User menu → **Organization** → complete **Setup** if prompted, then **Knowledge base**:

1. Create a note (draft), then **Publish** — or use setup wizard publish step.
2. Draft notes are **not** searchable; only published notes enter `tenant_knowledge` RAG.
3. Re-publish after edits replaces chunks via stable `tenant-content/{id}` source URI.
4. **Archive** removes a note from search.

Legacy direct ingest API still exists for operators; CMS is the supported path (Task 04).

### 4. Chat smoke test

1. Select agent **Knowledge Companion** (`knowledge_companion`).
2. Ask: „Wann Beatmungsschlauch wechseln laut unserer Notiz?“
3. Expect citation from ingested title/source.
4. Ask: „Patient Müller Allergien?“ → refusal (healthcare_ops prompt rules).

### 5. Invite colleague (Task 03)

**Platform admin → Users** — same `tenant_id`, `role=user`:

1. Create user (or use existing User B from `.env.e2e`).
2. Login as colleague → `/app/chat?agent=knowledge_companion`.
3. Ask the same question as in step 4 → expect the same `tenant_knowledge` source hit.
4. Optional automated check: `pytest tests/e2e/test_tenant_rag_isolation.py -m e2e`

### 6. Reload agents after plugin changes

Restart API or reload tools/agents if your deployment requires it for new
`plugins/agents/knowledge_companion/`.
