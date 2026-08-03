---
doc_id: planning-knowledge-companion-tasks
domain: agentlayer_docs
tags: [planning, knowledge-companion, tasks, backlog, vertical-profile]
---

## Knowledge companion — platform implementation tasks

Split backlog for the **industry-agnostic** strategy in
[`../knowledge-companion-plan.md`](../knowledge-companion-plan.md).

**Architecture:** one platform for all professions/industries. **Vertical profiles**
(e.g. healthcare) add policy and connectors on top — see
[`verticals/README.md`](./verticals/README.md).

**Rule:** ship **one task / one PR at a time**.

**Roles model (read first):** [`00-roles-and-scopes.md`](./00-roles-and-scopes.md)

### Platform tasks (all verticals)

| # | Task | Status | Depends on |
|---|------|--------|------------|
| 00 | [Roles and scopes (spec)](./00-roles-and-scopes.md) | **draft** | — |
| 01 | [Docs and boundaries](./01-docs-and-boundaries.md) | **done** | — |
| 02 | [RAG pilot + knowledge companion](./02-rag-pilot-knowledge-companion-agent.md) | **done** | 01 |
| 03 | [Tenant user onboarding](./03-tenant-user-onboarding.md) | **done** | 02 |
| 03b | [Identity roles + surfaces](./03b-identity-roles-and-surfaces.md) | **done** (baseline) | 03 |
| 04 | [CMS light (`tenant_content`)](./04-cms-light.md) | **done** | 02 |
| 05 | [Profession RBAC](./05-profession-rbac.md) | **done** (baseline) | 03b, 04 |
| 06 | [Review and approval workflow](./06-review-approval-workflow.md) | done | 05 |
| 07 | [Tenant templates](./07-tenant-templates.md) | done | 06 |

### Vertical profiles (optional; connectors after platform 01–06)

| Profile | Doc | Gated tasks |
|---------|-----|-------------|
| `healthcare_ops` | [healthcare-ops.md](./verticals/healthcare-ops.md) · [clinic web surface](./verticals/healthcare-ops/clinic-web-surface.md) | [H1–H3](./verticals/healthcare-ops/) |
| `field_service_ops` | _(stub)_ | — |
| `default_ops` | platform plan only | — |

### Recommended order

```text
01 (done) → 02 (done) → 03b (done) → 03 (done) → 04 (done) → 05 (done, baseline) → 06 → 07
```

### Principles

- **Three role layers:** site → tenant membership → profession — [`00-roles-and-scopes.md`](./00-roles-and-scopes.md).

- **Generic platform names** in code: `knowledge_companion`, `tenant_knowledge`, `tenant_content`.
- **No sensitive context data** in platform tasks 01–06 (define blocks per vertical).
- **Separate RAG:** `tenant_knowledge` vs `agentlayer_docs`.
- **Healthcare is one profile**, not the product name.

### Related docs

- Platform plan: [`../knowledge-companion-plan.md`](../knowledge-companion-plan.md)
- **Roles model:** [`./00-roles-and-scopes.md`](./00-roles-and-scopes.md)
- **Onboarding checklist:** [`./tenant-onboarding-checklist.md`](./tenant-onboarding-checklist.md)
- **Pilot runbook:** [`./RUNBOOK-pilot.md`](./RUNBOOK-pilot.md)
- **Pilot test plan (Phase 7):** [`./PILOT-TESTPLAN.md`](./PILOT-TESTPLAN.md)
- Healthcare redirect (old path): [`../healthcare-clinical-companion-plan.md`](../healthcare-clinical-companion-plan.md)
- RAG: [`../../features/rag.md`](../../features/rag.md)
