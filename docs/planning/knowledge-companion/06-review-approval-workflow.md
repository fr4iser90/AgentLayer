---
doc_id: healthcare-task-06-review-approval
domain: agentlayer_docs
tags: [healthcare, task, cms, workflow]
status: pending
---

## Task 06 — Review and approval workflow

**Status:** pending  
**Depends on:** [05](./05-clinical-rbac.md)  
**Goal:** Multi-step clinical content governance before production RAG ingest.

### Scope

#### Status workflow

- [ ] Extend CMS statuses: `draft` → `in_review` → `approved` → `published`
- [ ] Optional: `deprecated`, `archived`
- [ ] Only `published` triggers `tenant_knowledge` RAG ingest (unchanged rule).

#### Roles

- [ ] **Content Editor:** create/edit drafts, submit for review
- [ ] **Content Reviewer:** comment, approve or send back
- [ ] **Content Approver:** publish to production (+ RAG ingest)
- [ ] **Tenant Admin:** override in emergency (audited)

#### Features

- [ ] Reviewer queue UI or API list `in_review`
- [ ] Version history on each publish
- [ ] Diff view between versions (minimal: text diff)
- [ ] `tenant_knowledge_draft` domain for preview mode (editors/reviewers only;
      production `knowledge_companion` must not use it)

#### Audit

- [ ] Log: submit, review decision, publish, who approved, content version id

### Out of scope

- Two-person rule configuration UI (hardcode pilot policy first)
- External guideline import
- Legal e-signature

### Acceptance criteria

- [ ] Editor cannot publish directly without Approver role.
- [ ] Reviewer can reject back to draft with comment.
- [ ] Published version visible in companion with approver metadata.
- [ ] Draft / in_review never in production RAG.

### Exit criteria

- [ ] Phase 1 MVP complete for governed team use (still no PHI).
- [ ] README: tasks 01–06 marked done when applicable.

### Next task (gated)

→ [07 — FHIR read-only](./07-fhir-read-only.md) — **only after privacy/clinical sign-off**
