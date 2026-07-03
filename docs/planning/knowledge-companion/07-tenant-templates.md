---
doc_id: knowledge-task-07-tenant-templates
domain: agentlayer_docs
tags: [knowledge-companion, task, tenant, templates]
status: done
---

## Task 07 (platform) — Tenant templates

**Status:** done  
**Depends on:** [06 — Review and approval workflow](./06-review-approval-workflow.md)  
**Goal:** Platform Admin can create a **new live tenant from a template** instead
of hand-configuring every org.

### Scope

- [x] `tenant_templates` store (JSON file or DB table)
- [x] Seed templates: `tpl_default_ops`, `tpl_healthcare_ops`
- [x] Optional demo content via `seed_demo_content` (synthetic Markdown from template glob)
- [x] API: `POST /v1/admin/tenants` accepts `template_id`, `seed_demo_content`
- [x] Clone on create: `vertical_profile`, RAG domain allowlist, agent policy,
      profession role templates, workflow defaults — **not** RAG chunks or users
- [x] Admin UI: "Create tenant from template"
- [x] Document template authoring for Platform Admin

### Out of scope

- Self-service signup without Platform Admin
- Cross-tenant template editing by Tenant Admin
- Copying production content between tenants

### Acceptance criteria

- [x] New tenant from `tpl_healthcare_ops` has `vertical_profile` and empty
      `tenant_knowledge` (unless `seed_demo_content=true` for demo only).
- [x] Tenant B created from template cannot see Tenant A RAG data.
- [x] Template update does not retroactively change existing live tenants.

### Template authoring

Add a JSON file under `content/tenant-templates/<id>.json`:

```json
{
  "id": "tpl_my_vertical",
  "name": "Human label",
  "description": "Shown in Admin → Users template picker",
  "vertical_profile": "default_ops",
  "departments": [{ "slug": "ops", "name": "Operations" }],
  "profession_roles": [
    { "slug": "content_editor", "name": "Editor", "role_kind": "content_editor", "content_categories": [] }
  ],
  "workflow_defaults": { "content_review_required": true },
  "enabled_agent_ids": ["general", "knowledge_companion"],
  "enabled_tool_domains": ["rag", "knowledge", "shared"],
  "seed_content_glob": "content/my-pilot/*.md"
}
```

**Capability fields (optional):**

| Field | Stored as | Effect |
|-------|-----------|--------|
| `enabled_agent_ids` | `chat.allowed_agent_ids` + `delegate.allowed_agent_ids` | Non-admin users only see these agents in chat/delegation |
| `enabled_tool_domains` | `tools.allowed_domains` | Hide tools whose package `domain` is not listed (`shared` always allowed) |

Empty arrays = no restriction (full platform catalog for that tenant).

Restart is not required — templates are loaded on each API call (cached in-process until reload).

### API

- `GET /v1/admin/tenant-templates` — list blueprints
- `POST /v1/admin/tenants` — `{ "name", "template_id?", "seed_demo_content": false }`

### Related

- Plan: [`../knowledge-companion-plan.md`](../knowledge-companion-plan.md) —
  *Tenant Provisioning And Templates*
