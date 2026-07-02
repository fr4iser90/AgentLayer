---
doc_id: healthcare-task-06-review-approval
domain: agentlayer_docs
tags: [healthcare, task, cms, workflow]
status: done
---

## Task 06 — Review and approval workflow

**Status:** done  
**Depends on:** [05](./05-profession-rbac.md)  
**Goal:** Multi-step clinical content governance before production RAG ingest.

### Scope

#### Status workflow

- [x] Extend CMS statuses: `draft` → `in_review` → `approved` → `published`
- [x] Optional: `deprecated`, `archived`
- [x] Only `published` triggers `tenant_knowledge` RAG ingest (unchanged rule).

#### Roles

- [x] **Content Editor:** create/edit drafts, submit for review
- [x] **Content Reviewer:** comment, approve or send back
- [x] **Content Approver:** publish to production (+ RAG ingest)
- [x] **Tenant Admin:** override in emergency (audited via `?override=true`)

#### Features

- [x] Reviewer queue UI or API list `in_review`
- [x] Version history on each publish
- [x] Diff view between versions (minimal: unified text diff)
- [x] `tenant_knowledge_draft` domain for preview mode (editors/reviewers only;
      production `knowledge_companion` must not use it)

#### Audit

- [x] Log: submit, review decision, publish, who approved, content version id

### Out of scope

- Two-person rule configuration UI (hardcode pilot policy first)
- External guideline import
- Legal e-signature

### Acceptance criteria

- [x] Editor cannot publish directly without Approver role.
- [x] Reviewer can reject back to draft with comment.
- [x] Published version visible in companion with approver metadata.
- [x] Draft / in_review never in production RAG.

### Exit criteria

- [x] Phase 1 MVP complete for governed team use (still no PHI).
- [x] README: tasks 01–06 marked done when applicable.

### Next task (gated)

→ [07 — Tenant templates](./07-tenant-templates.md)
