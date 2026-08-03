---
doc_id: planning-knowledge-companion
domain: agentlayer_docs
tags: [planning, knowledge-companion, tenants, governance, cms, rag, vertical-profile]
---

## Purpose

This document is the **industry-agnostic** strategy, roadmap, drift analysis, and
implementation plan for the AgentLayer **tenant knowledge companion** — a
governed, role-aware assistant over **tenant-authored operational knowledge**
for **any profession or industry**.

It is intentionally a planning document, not an ADR. Promote specific decisions
to ADRs only when a slice locks security, tenancy, or regulated-data boundaries.

The near-term MVP: tenant-scoped knowledge (RAG + optional CMS), profession roles,
qualifications, publish workflow — **without regulated third-party context data**
(customer PHI, live ERP records, etc.) until vertical gates are met.

**Healthcare** is documented as the **first vertical profile** (`healthcare_ops`),
not the platform itself. See
operator-local vertical docs (not published in this repository).

**Implementation backlog (one PR per task):**
[`docs/planning/knowledge-companion/README.md`](./knowledge-companion/README.md)

**Deployment mode:** the knowledge companion product assumes
`deployment_mode = multi_tenant` (firms/orgs). For homelab-style **agent system**
(installation without firms — admin + users only), see
[`knowledge-companion/00-roles-and-scopes.md`](./knowledge-companion/00-roles-and-scopes.md#deployment-mode-chosen-once-in-appsetup).

## North Star

The knowledge companion is a universal **role-aware interface for operational
teams** in any industry. It recognizes who is using it, which tenant and
department they belong to, which profession role and qualifications apply, and
which content, tools, and recommendations are allowed.

It answers from **approved tenant content**, cites sources and versions, and
escalates when the request needs sensitive context data, a missing qualification,
or a human decision.

The CMS (`tenant_content`) is the controlled knowledge base: SOPs, checklists,
manuals, onboarding paths, FAQs, and role-specific summaries with
draft/review/publish workflows.

### Example industries (same platform)

| Industry | Example professions | Example content |
|----------|--------------------|-----------------|
| Healthcare | anesthesia nurse, OTA | checklists, device intervals |
| Field service | technician, dispatcher | repair procedures, parts |
| Manufacturing | operator, maintenance | machine setup, safety checks |
| IT / internal ops | L1 support, admin | runbooks, onboarding |
| Retail / logistics | shift lead, picker | store procedures, safety |

## Vertical Profiles

Build **one generic platform**; enable **vertical profiles** as configuration.

See [`knowledge-companion/verticals/README.md`](./knowledge-companion/verticals/README.md).

| Layer | Responsibility |
|-------|----------------|
| **Platform** | `knowledge_companion`, `tenant_knowledge`, `tenant_content`, profession RBAC |
| **Vertical profile** | prompt rules, blocked patterns, connectors, sample content, evaluation |

Platform naming (use in code):

| Concept | Id / name |
|---------|-----------|
| Agent | `knowledge_companion` |
| RAG domain (published) | `tenant_knowledge` |
| RAG domain (draft preview) | `tenant_knowledge_draft` |
| CMS | `tenant_content` |
| Profession role | `profession_role` (tenant-defined values) |
| Tools (MVP) | `knowledge.search`, `knowledge.read_published` |
| Profile config | `vertical_profile` e.g. `default_ops`, `healthcare_ops` |

Platform invariants (all verticals):

- tenant-scoped content and RAG isolation
- draft / review / publish workflow
- source citation and version in answers
- disclaimer levels (learning aid, draft, approved)
- separate from `agentlayer_docs` product RAG
- no mixing workspace coding RAG into tenant knowledge search

**Do not** fork the runtime per industry. Swap profile, content, and connectors.

## Sensitive Context Data Strategy (platform)

Phase 1 for **every** vertical: operate on **self-authored tenant knowledge
only**. Do not ingest or answer from live systems holding regulated or
customer-specific data until vertical gates are documented and implemented.

Examples of sensitive context (by vertical):

| Vertical | Sensitive context (defer to vertical doc + gates) |
|----------|---------------------------------------------------|
| Healthcare | PHI, vitals, FHIR patient resources — profile `healthcare_ops` (details operator-local) |
| Field service | customer site credentials, live work orders |
| IT ops | live credentials, production customer data |
| Any | PII, secrets, copied copyrighted manuals without permission |

Common gates before sensitive context:

- tenant privacy / compliance review
- role and context authorization
- context-specific audit logging
- source attribution for every external fact
- read-only integration boundary first
- retention and redaction policy
- incident and escalation runbooks

Vertical-specific regulation (e.g. healthcare MDR) belongs in the vertical profile
doc, not in platform code paths.

## Self-Authored MVP Content Boundary

The safest first MVP content is **self-authored operational knowledge**, not
copied official or vendor documents. Content is searchable through RAG when
clearly labeled, versioned, and kept free of sensitive context data.

Allowed MVP examples (any industry):

- self-written workflow notes and checklists
- maintenance / setup / cleanup procedures
- interval reminders (filters, parts, consumables)
- onboarding notes and FAQs
- simulated scenarios without real identifiers

Avoid in the MVP:

- scanned or copied official SOPs, vendor manuals, or licensed guideline text
- screenshots from production systems with customer/user identifiers
- live exports from ERP, CRM, KIS, or ticketing with PII
- claims that content is an **official** approved procedure unless formally published

Every MVP content item should show:

- author, tenant, version, dates
- status: personal note, team draft, reviewed, approved, published
- source type: self-authored, imported with permission, external reference
- disclaimer level: learning aid, local draft, approved content

The companion presents self-authored content as **orientation / learning aid**,
not as an official order or replacement for approved procedures and local policy.

Healthcare-specific content rules: see
the `healthcare_ops` vertical profile (operator-local detail docs).

## Current AgentLayer Baseline

AgentLayer already has several platform concepts that map well to the knowledge
companion:

- Tool registry and capability-based routing are documented in
  `docs/adr/0001-tool-and-agent-architecture.md`.
- Capability allow/block/confirm gates are documented in
  `docs/adr/0003-capability-governance.md`.
- Agent governance already models tenant overrides, prompt versions, model
  policy, tool policy, and effective Agent preview in
  `docs/architecture/agent-governance.md`.
- The strategic design already defines Identity/Tenant, Tool Registry, Agent
  Governance, Knowledge/RAG, Model Routing, Evaluation/Harness, and Audit
  direction in `docs/architecture/strategic-design.md`.
- Tool policy currently supports effective enablement, `min_role`, and
  `allowed_tenant_ids` in `apps/backend/domain/plugin_system/tool_policy.py`.
- Runtime tool execution enforces tool policy and capability governance in
  `apps/backend/domain/plugin_system/tools.py`.
- Admin agent config APIs already expose tenant-scoped effective config,
  fingerprints, snapshots, and changelog in
  `apps/backend/api/agents/controllers/agent_config_admin_api.py`.

This means the knowledge companion should extend existing governance patterns
instead of inventing a separate vertical runtime.

## Current Drifts And Gaps

The current platform is a generic agent runtime, not yet a tenant knowledge product.
The main drifts from the target are:

- Identity is still too simple for profession-based authorization. Current user roles
  are close to `admin`/`user`; tenant knowledge use needs profession, department,
  location, active shift, qualifications, and certifications.
- Tool policy is tenant-aware but not yet profession-context-aware. Vertical
  profiles add role, department, location, and qualification checks.
- There is no tenant content CMS yet. Current RAG/knowledge primitives need a
  controlled editorial model with draft/review/publish, expiry, source, and
  content-owner metadata.
- RAG ingest is **admin-only** today (`POST /v1/admin/rag/ingest`); Content
  Editor and Approver roles with publish-triggered ingest are not implemented.
- RAG domains are configurable but tenant knowledge separation (`tenant_knowledge` vs
  `agentlayer_docs`) and per-Agent search policy are documented here but not
  enforced in a dedicated `knowledge_companion` agent yet.
- There are no vertical connector packs yet (healthcare FHIR/PDMS documented under
  operator-local vertical docs).
- Audit exists as a platform direction, but knowledge answers need stronger
  structure: who asked, which context was active, which source version was used,
  which tool ran, and whether the answer was advisory or blocked.
- The tool capability model needs a risk tier and data class in addition to
  `domain.action`.
- Agent evaluation needs content-quality and escalation scenarios per vertical
  profile.
- Documentation paths still contain some historical references to `src/...`
  while the active backend paths are under `apps/backend/...`. New docs should
  cite current paths.

## Tenant Model

Each organization (company, hospital group, team) is a **tenant**. A tenant
owns its knowledge content, users, integrations, policies, audit logs, and tool
configuration.

Recommended tenant-level objects:

- tenant profile: name, region, data residency, enabled features, `vertical_profile`
- departments and locations (tenant-defined)
- profession roles (tenant-defined templates)
- qualifications and certifications
- content collections (SOPs, checklists, runbooks, FAQs)
- tool policies per role and context
- integration configs (SSO, LDAP/HR, optional vertical connectors)
- governance workflows: reviewers, approvers, expiry policy

Tenant admins are required so each organization can configure staff, content,
and policies without platform operator involvement.

## Tenant Provisioning And Templates

A **tenant** is one organization’s isolated workspace. A **tenant template** is a
**blueprint** used when creating a new tenant — not a shared production tenant
that multiple customers use at once.

### Three provisioning modes

| Mode | Who creates it | Purpose | Production data? |
|------|----------------|---------|------------------|
| **Live tenant** | Platform or Tenant Admin | real org (clinic, team, company) | yes (their content) |
| **Demo tenant** | Platform Admin | showcase, training, sales | sample/synthetic only |
| **Tenant template** | Platform Admin | clone config when spawning new tenants | no (blueprint only) |

```text
Tenant template (blueprint, not shared runtime)
  -> Platform Admin: "Create tenant from template"
  -> New live tenant (empty content, copied config)
  -> Tenant Admin onboarded
  -> Team adds own tenant_knowledge content
```

### What a tenant template should include

Templates copy **configuration**, not another customer’s data:

- `vertical_profile` (e.g. `healthcare_ops`, `field_service_ops`, `default_ops`)
- default `rag_tenant_shared_domains` (`tenant_knowledge`, …)
- enabled agents (`knowledge_companion` policy)
- enabled tool capabilities (`knowledge.search`, …)
- default profession role templates (names only, no users)
- default department list (optional starter set)
- default qualification types (optional)
- content workflow defaults (draft → review → publish)
- disclaimer and blocked-query policy from vertical profile
- optional **seed content** flag: copy demo Markdown into new tenant (off by default for live orgs)

Templates should **not** include:

- users or passwords from another tenant
- RAG chunks from another tenant
- PHI, customer PII, or copied official documents
- live connector credentials

### Planned template catalog (examples)

| Template id | Vertical profile | Intended use |
|-------------|------------------|--------------|
| `tpl_default_ops` | `default_ops` | generic team / internal ops |
| `tpl_healthcare_ops` | `healthcare_ops` | hospital department pilot |
| `tpl_field_service_ops` | `field_service_ops` | technicians / maintenance (stub) |
| `tpl_demo_healthcare` | `healthcare_ops` | demo tenant with sample checklists |
| `tpl_demo_default` | `default_ops` | generic demo / sandbox |

Naming convention:

- `tpl_*` — blueprint used to **create** tenants
- `demo_*` — pre-provisioned **demo tenants** (optional, read-heavy)
- live tenant slug — org-chosen, e.g. `klinik-pilot-nord`, `acme-field-service`

### Who does what

**Platform Admin (you / operator):**

- maintain tenant templates and demo tenants
- create live tenant from template for a new customer or pilot
- assign first Tenant Admin user

**Tenant Admin (customer / department lead):**

- invite users into **their** tenant only
- define profession roles and departments (or adjust template defaults)
- publish `tenant_knowledge` content
- never sees other tenants’ data

**End users:**

- search/read in their tenant via `knowledge_companion`
- no cross-tenant access

### Solo pilot (you, now)

You do **not** need a template engine on day one. Minimum path:

1. Create one live tenant (or use default `tenant_id=1`).
2. Set `vertical_profile: healthcare_ops` manually.
3. Ingest self-authored notes into `tenant_knowledge`.
4. Invite colleagues into the **same** tenant.

Add templates when you onboard a **second** org or vertical and repeat the same setup often.

### Implementation note (future task)

Not built yet. Likely surface:

- `POST /v1/admin/tenants` body: `{ "name", "template_id", "seed_demo_content": false }`
- template store: JSON or DB table `tenant_templates`
- clone: operator settings slice, agent policy, role templates — **not** RAG rows

Track as [Task 07 — Tenant templates](./knowledge-companion/07-tenant-templates.md).

## Role And Permission Model

Use a combined RBAC/ABAC model.

RBAC answers: what role does the user have?

ABAC answers: under which attributes may that role act?

Context-based policy answers: is the current situation valid for this action?

Core global roles:

- Platform Owner: manages platform-level defaults and tenant lifecycle.
- Global Security Admin: manages global security policy and incident controls.
- Global Compliance Auditor: reviews cross-tenant compliance metadata without
  access to tenant sensitive data by default.
- Integration Engineer: manages connector templates and technical onboarding.
- Model Governance Admin: manages model profiles, prompt governance, and
  evaluation promotion gates.

Core tenant roles:

- Tenant Admin: manages users, departments, tenant policies, and feature flags.
- Domain Admin: manages domain workflow configuration and profession role mappings.
- Content Editor: writes content drafts but cannot publish.
- Content Reviewer: performs domain review.
- Content Approver: publishes approved content.
- Department Admin: manages department-scoped users, collections, and local SOPs.
- Tool Admin: activates tools per role, department, and risk level.
- Audit Viewer: reads tenant audit logs and reports.
- End User: uses the companion according to role, context, and qualifications.

Profession roles (tenant-configurable). Examples:

| Vertical | Example profession roles |
|----------|-------------------------|
| Healthcare | anesthesia nurse, OTA, ICU nurse — profile `healthcare_ops` (details operator-local) |
| Field service | technician, senior tech, dispatcher |
| IT ops | L1 support, sysadmin, on-call |
| Manufacturing | operator, maintenance, shift lead |

## Certifications And Qualifications

Certifications and qualifications should be first-class policy inputs, not free
text in a prompt.

Recommended fields:

- qualification id and display name
- issuing authority
- tenant or global scope
- valid from / valid until
- verification status
- evidence reference
- required renewal interval
- department/device/procedure scope
- source system: HR, LMS, manual admin entry, SSO claim
- audit history

Examples:

- "Drager Perseus device training valid until 2027-02-01"
- "ACLS valid until 2026-11-30"
- "Local cardiac anesthesia induction SOP completed"
- "Medication pump certification for OR area"
- "Trainee may view checklist but not receive autonomous action prompts"

Policy examples:

- A user may read a device manual if they belong to the tenant.
- A user may receive device setup checklist steps only if assigned to the OR
  department.
- A user may receive role-specific emergency checklist guidance only if their
  active role and department match.
- A user may not receive patient-context advice unless they have an active
  encounter context and a matching clinical role.

## Tool Management

Healthcare tools should extend the existing Tool Registry model. The platform
already has `TOOL_DOMAIN`, `TOOL_CAPABILITIES`, `min_role`, tenant filtering,
and capability gates. Use **generic knowledge tools** for MVP; add healthcare
connector tools only in later gated tasks.

Recommended platform tool metadata:

- `TOOL_DOMAIN`: `knowledge` (MVP), later vertical packs e.g. `healthcare_fhir`,
  `healthcare_devices`
- `TOOL_CAPABILITIES`: examples below
- risk tier: low, medium, high, restricted
- data class: public, tenant_internal, staff_sensitive, patient_sensitive,
  device_realtime
- action class: read, explain, recommend, notify, write
- required qualifications
- required clinical context
- requires confirmation
- shadow-mode eligible
- audit level
- source attribution requirement

Example capability strings (platform + healthcare vertical):

**Platform (all verticals, MVP):**

- `knowledge.search`
- `knowledge.read_published`
- `knowledge.publish`
- `training.read`
- `training.verify_qualification`

**Healthcare vertical pack (later, gated):**

- `healthcare.ops.read_schedule`
- `healthcare.fhir.read_patient`
- `healthcare.fhir.read_allergy`
- `healthcare.fhir.read_observation`
- `healthcare.devices.read_vitals`
- `healthcare.alerts.notify`

Initial phase should only enable low-risk platform tools:

- `knowledge.search`
- `knowledge.read_published`
- `training.read`
- `training.verify_qualification`

Do not enable patient, device, notification, or write tools in the first MVP.

## CMS Strategy

The CMS should be a tenant-scoped **tenant content** service (`tenant_content`).
It can later connect to RAG/vector search, but its canonical content model must
remain structured and auditable.

Minimum content fields:

- content id
- tenant id
- title
- content type: SOP, checklist, device manual, emergency algorithm, medication
  reference, onboarding material
- body: Markdown or structured blocks
- language
- target roles
- target departments
- required qualifications
- tags and ontology mappings
- content owner (clinical owner in healthcare pilot)
- editor/reviewer/approver
- status: draft, in_review, approved, published, deprecated, archived
- version
- effective date
- expiry/review date
- source references
- external guideline references
- attachments
- audit history

The companion should only answer from published content in production mode.
Draft content may be available in an admin preview mode, clearly labeled.

## Tenant Admin Operations

> **Canonical roles model:** [`knowledge-companion/00-roles-and-scopes.md`](./knowledge-companion/00-roles-and-scopes.md)  
> Three layers: **Site** (deployment) → **Tenant membership** → **Profession/content**.

Tenant admins configure who may use the knowledge companion, which profession
roles and departments apply, and which content and tools are available. This section
describes the target operating model. Most of it is **not implemented yet** in
AgentLayer; today only platform `admin` / `user` roles exist and RAG ingest is
admin-only. See `docs/features/operator-agent.md` and `docs/features/rag.md`.

### Current State Vs Target

| Concern | Today (AgentLayer) | Target (tenant knowledge MVP) |
|---------|-------------------|-------------------------------|
| User creation | `POST /v1/admin/users` with `role`, `tenant_id` | Tenant Admin invites users into their tenant |
| Platform role | `admin` or `user` | Keep platform role separate from profession role |
| Profession role | not modeled | tenant-configurable profession + department |
| Qualifications | not modeled | assigned per user with expiry |
| Content upload | admin RAG ingest only | Content Editor writes; Approver publishes |
| RAG ingest trigger | manual admin HTTP | publish event triggers `tenant_knowledge` ingest |
| Tool access | tool policy + `min_role` | profession role + department + qualification |

Platform `admin` should not be confused with **Tenant Admin**. A deployment may
have one platform admin who bootstraps tenants; each tenant then manages its own
staff, content, and policies.

**Web UI separation (pilot):**

| Surface | Route | Scope |
|---------|-------|-------|
| Platform admin | `/app/admin` | Operator: embedding, RAG domains, all tenants |
| Organization | `/app/org` | Tenant Admin: team knowledge, future team/users |

Task **03b** will restrict `/org` to tenant membership admins (`tenant_admin`) without
access to `/admin`. Task **05** adds profession/content roles (Layer 3).

### Tenant Admin Responsibilities

A Tenant Admin should be able to:

1. **Configure the tenant profile** — name, enabled features, default language,
   disclaimer text, content review policy.
2. **Define departments and locations** — e.g. anesthesia, OR 3, ICU.
3. **Define profession roles** — e.g. anesthesia nurse, OTA, trainee (healthcare
   pilot); map each to allowed content categories and tool capabilities.
4. **Invite and assign users** — link a user to one or more profession roles,
   departments, and optional qualifications.
5. **Assign content permissions** — who may edit, review, approve, or only read.
6. **Enable knowledge tools** — activate low-risk tools such as
   `knowledge.search` for selected roles; keep healthcare connector tools off.
7. **Configure RAG domains** — ensure `tenant_knowledge` is tenant-shared; keep
   platform docs in `agentlayer_docs` separate.
8. **Set vertical profile** — e.g. `healthcare_ops` for PHI refusal and disclaimer
   copy on the `knowledge_companion` agent.
9. **Review audit logs** — who published content, who searched what, which source
   versions were cited.

### MVP Role Matrix (Example)

Use this as the first documented permission matrix for a pilot tenant.

| Role | CMS write | CMS review | CMS publish | RAG search (tenant) | RAG search (platform) | Invite users | Manage roles |
|------|-----------|------------|-------------|---------------------|----------------------|--------------|--------------|
| Tenant Admin | yes | yes | yes | yes | yes | yes | yes |
| Domain Admin | yes | yes | no | yes | yes | no | yes |
| Content Editor | yes | no | no | yes | optional | no | no |
| Content Reviewer | no | yes | no | yes | optional | no | no |
| Content Approver | no | yes | yes | yes | optional | no | no |
| End User | no | no | no | yes | optional | no | no |
| Trainee | no | no | no | limited | no | no | no |

Notes:

- **Publish** means both CMS status `published` and RAG ingest for
  `tenant_knowledge`.
- **Trainee** may see onboarding content only until qualifications are assigned.
- Platform RAG (`agentlayer_docs`) is optional for end users; enable only if they
  need AgentLayer product help in the same chat surface.

### How Tenant Admins Define Roles (Target Flow)

```text
Tenant Admin
  -> create department(s)
  -> create profession role template(s)
  -> define role -> content category access
  -> define role -> tool capability access
  -> invite user (email / SSO)
  -> assign profession role + department
  -> assign qualification(s) with valid_until
  -> attach vertical_profile (e.g. healthcare_ops) if needed
  -> effective policy resolved per request
```

Profession roles are **tenant data**, not hard-coded agent ids. The
`knowledge_companion` Agent should consume effective policy and vertical profile;
it should not embed role names in its prompt as the source of truth.

### Interim MVP Before Full Profession RBAC

Until profession roles are implemented, a practical bootstrap is:

1. Use platform `admin` as Tenant Admin for the pilot tenant.
2. Use platform `user` for invited colleagues who may **search only**.
3. Keep all content self-authored and published by the admin account.
4. Store intended profession role and department in content metadata even if runtime
   filtering is not enforced yet.
5. Set `vertical_profile: healthcare_ops` in tenant config when available.
6. Document the gap explicitly in release notes and admin UI.

This keeps the pilot usable without pretending fine-grained RBAC already exists.

## RAG Domain Model And Search Policy

Tenant knowledge and AgentLayer product documentation must stay **separable**.
Use RAG **domains** on the existing pgvector stack; do not mix unrelated corpora
in one default search.

AgentLayer already supports:

- **tenant + user** scoped documents (private by default)
- **tenant-wide** domains via `rag_tenant_shared_domains` in operator settings
- **workspace-scoped** documents for coding projects (separate from global domains)

See `docs/features/rag.md` and `apps/backend/infrastructure/rag/rag_core.py`.

### Domain Catalog

| Domain | Purpose | Visibility | Used by |
|--------|---------|------------|---------|
| `agentlayer_docs` | AgentLayer product docs, API, architecture | tenant-wide | Operator, General, support |
| `tenant_knowledge` | self-authored team notes, checklists, workflows | tenant-wide | knowledge_companion |
| `tenant_knowledge_draft` | preview only; not for production answers | editors/reviewers | admin preview |
| `user_notes` | personal learning notes | user-private | optional personal agent |
| `workspace_docs` | coding project markdown | workspace-bound | coding agents only |

Rules:

- Never store patient data in any RAG domain in Phase 1.
- Do not put tenant knowledge content into `agentlayer_docs`.
- Do not put AgentLayer platform docs into `tenant_knowledge`.
- Add `tenant_knowledge` to `rag_tenant_shared_domains` when the tenant knowledge MVP
  ships; keep the list explicit rather than searching all domains by default.

### Tenant Isolation

All RAG rows are keyed by `tenant_id`. Tenant A must never retrieve Tenant B
chunks. Tenant-wide domains still filter by `tenant_id`; they only remove the
per-user filter inside the same tenant.

Cross-tenant platform documentation, if ever needed, belongs in a separate
deployment or a dedicated platform tenant — not mixed into hospital tenant data.

### Search Modes For Agents

Configure each Agent with an explicit retrieval policy. Do not rely on the model
to pick the right corpus implicitly.

**Mode 1 — Platform only**

- Domain: `agentlayer_docs`
- Use when: user asks how AgentLayer works, admin configuration, tool help
- Agent: `operator`, `general` (product questions)

**Mode 2 — Tenant knowledge only**

- Domain: `tenant_knowledge`
- Use when: user asks about local workflows, checklists, intervals, onboarding
- Agent: `knowledge_companion` (default; `vertical_profile: healthcare_ops` for pilot)

**Mode 3 — Combined (explicit)**

- Order: search `tenant_knowledge` first; if low confidence or platform intent
  detected, also search `agentlayer_docs`
- Use when: single UI serves both tenant knowledge and product help
- Requirement: answer must label which corpus each citation came from

**Mode 4 — Personal only**

- Domain: `user_notes`
- Use when: private study notes; never mixed into team knowledge answers without
  explicit user opt-in

Workspace-bound coding RAG remains unrelated to tenant knowledge search. When a workspace
is active, existing AgentLayer behavior already excludes global domains.

### Knowledge Companion Default Policy (Recommended)

```text
knowledge_companion:
  vertical_profile: healthcare_ops   # optional; omit for generic profession use
  default_search_domains: [tenant_knowledge]
  optional_search_domains: [agentlayer_docs]
  forbidden_domains: [tenant_knowledge_draft, user_notes, workspace_docs]
  require_source_citation: true
  require_content_version: true
  block_patient_specific_queries: true   # healthcare_ops profile only
  fallback_message: escalate to human / official source when no published hit
```

Optional UI alias: expose the same agent as `clinical_companion` when
`vertical_profile=healthcare_ops` without forking runtime code.

### Mapping To Existing Config

Today, add `tenant_knowledge` alongside `agentlayer_docs` in:

- operator setting **`rag_tenant_shared_domains`**
- ingest: **Admin → Interfaces → Memory & RAG → Team knowledge** (or `POST /v1/admin/rag/ingest` with `domain: "tenant_knowledge"`)
- tool calls: `rag_search({ query, domain: "tenant_knowledge" })`

Future work: move ingest from platform-admin-only to Content Approver with
tenant-scoped authorization and publish hooks.

## Content Upload And RAG Ingest Workflow

Content enters the system as governed CMS data first; RAG is a **published
read model**, not the authoring store.

### End-To-End Flow

```text
Content Editor
  -> create Markdown draft in CMS
  -> set metadata (role, department, disclaimer, source type)
Content Reviewer
  -> review for clinical plausibility and copyright boundary
Content Approver
  -> set status = published
  -> trigger RAG ingest into domain tenant_knowledge
Knowledge Companion (healthcare_ops profile)
  -> rag_search / knowledge.read_published
  -> answer with title, version, author, disclaimer
Audit
  -> log publish event + answer citations
```

Draft and in-review content must **not** appear in production RAG answers.

### Upload Rules (MVP)

Allowed uploads:

- Markdown or plain text written by the author
- self-authored checklists and workflow notes
- structured metadata (roles, departments, qualifications, expiry)

Rejected or quarantined uploads:

- PDF/scans of official SOPs or manufacturer manuals
- copied guideline text
- images or screenshots from clinical systems
- any patient-identifiable content

Validation should check:

- no obvious patient identifiers in text
- `source_type = self-authored` unless explicit permission exists
- disclaimer level is set
- target roles and departments are set

### Ingest Mechanics

**Today (interim):**

- Tenant Admin publishes via **Organization → Knowledge base** (`/app/org/knowledge`).
- Platform operator enables RAG + `tenant_knowledge` domain under **Platform admin → Interfaces → Memory**.

**Target:**

- Publish action enqueues ingest for that content version only.
- Re-publish replaces prior chunks for the same `source_uri` / content id.
- Deprecate/archive removes or hides chunks from search.
- Embedding model or chunk setting changes trigger tenant clinical re-ingest.

Ingest payload should carry CMS metadata into RAG document fields where
possible: `title`, `source_uri`, domain, and later custom metadata for role and
department filters at retrieval time.

### Personal Vs Team Content

| Type | CMS status | RAG domain | Who sees it |
|------|------------|------------|-------------|
| Personal learning note | personal note | `user_notes` | author only |
| Team draft | draft / in_review | `tenant_knowledge_draft` | editors/reviewers |
| Published team content | published | `tenant_knowledge` | tenant users by role |
| Platform help | n/a | `agentlayer_docs` | tenant-wide |

Do not promote personal notes to team content without an explicit publish action
and reviewer approval.

### Answer Contract

When the knowledge companion answers from RAG, every response should include:

- content title
- content version or updated date
- author or owning department
- disclaimer level (learning aid / local draft / approved)
- explicit statement when no published content matched

Example footer pattern:

```text
Sources: "Beatmungsschlauch Wechselintervall (Notiz)" v3, self-authored,
learning aid — not an official SOP. Verify against local policy.
```

### Re-Ingest And Deletion

- **Edit published content** -> new version -> re-ingest -> replace chunks for
  that `source_uri`.
- **Deprecate content** -> remove from search or mark hits as deprecated in UI.
- **Delete content** -> purge RAG rows for that document id.
- **Tenant offboarding** -> purge all `tenant_knowledge` rows for that tenant.

## Phased Roadmap

### Phase 0 - Discovery And Safety Framing

Goal: define a simple, safe pilot **without sensitive context data**.

Deliverables:

- confirm first tenant and vertical profile (e.g. `default_ops` or `healthcare_ops`)
- choose two initial profession roles
- collect 20-50 self-authored documents
- define content workflow and content owner model
- define tenant roles and admin permissions
- create risk register and privacy assumptions

Exit criteria:

- no regulated context data in MVP scope
- content schema and role model approved

### Phase 1 - Tenant Knowledge Companion MVP (platform)

Goal: useful role-aware knowledge for any pilot vertical — self-authored content only.

Scope:

- `tenant_content` CMS model
- `knowledge.*` search/read tools
- profession role filtering (basic)
- tenant admin setup
- editor/reviewer/approver workflow
- source and version display
- answer audit event

Out of scope (platform):

- live integrations with customer/patient/ERP systems
- vertical connector packs (see `verticals/`)

### Phase 2 - Context Without Sensitive External Data

Goal: operational context (shift, location, assignment) without regulated exports.

### Phases 3+ — Vertical connectors (not platform)

Regulated or live-system integration is **per vertical profile**, not core platform.

Example: healthcare FHIR/PDMS/ML →
operator-local vertical docs (not in this repository).

Other verticals add their own connector docs when needed.

## Complex Implementation Plan

Ship using the split task backlog — **one task / one PR at a time**:
[`knowledge-companion/README.md`](./knowledge-companion/README.md)

Summary mapping (details and acceptance criteria live in each task file):

| Task | Theme |
|------|--------|
| 01 | Docs and boundaries (**done**) |
| 02 | RAG pilot + `knowledge_companion` (**done** — see runbook) |
| 03 | Tenant user onboarding |
| 04 | CMS light (`tenant_content`) + publish → RAG |
| 05 | Profession RBAC |
| 06 | Review and approval workflow |
| 07 | Tenant templates (`tpl_*` → new live tenant) |
| — | **Vertical profiles** (e.g. healthcare H1–H3): [`verticals/`](./knowledge-companion/verticals/README.md) |

The slices below remain the architectural breakdown; implement them through the
numbered tasks above rather than in one shot.

### Slice A - Planning Artifacts

- Create this planning document.
- Add a healthcare section to the docs index.
- Draft future ADR candidates:
  - tenant profession authorization model
  - tenant content publication model
  - knowledge tool risk tiers
  - healthcare patient data boundary and audit model (vertical only)

### Slice B - Domain Model Design

- Add conceptual domain objects for:
  - TenantProfile
  - Department
  - ProfessionRole
  - Qualification
  - TenantContent
  - ContentVersion
  - ContentApproval
  - VerticalProfile
  - KnowledgeToolPolicy
  - RequestContext
  - KnowledgeAuditEvent
- Keep these separate from existing simple `User.role` until a migration plan is
  ready.
- Decide whether profession roles are stored as identity attributes, tenant policy
  objects, or both.

### Slice C - Policy Resolution

- Extend effective policy resolution to combine:
  - platform default
  - tenant policy
  - department policy
  - user role
  - qualifications
  - active context
  - tool risk tier
  - data class
- Build an explanation API for "why was this content/tool allowed or blocked?"
- Add tests for deny-by-default behavior.

### Slice D - CMS MVP

- Implement tenant-scoped `tenant_content` tables.
- Add draft/review/publish states.
- Add version history and source references.
- Add content-origin metadata for self-authored, permissioned import, and
  external reference content.
- Add an MVP ingestion rule that rejects copied official documents, scans,
  patient screenshots, and patient identifiers by default.
- Wire publish action to RAG ingest for domain `tenant_knowledge` (see
  **Content Upload And RAG Ingest Workflow** above).
- Register `tenant_knowledge` in `rag_tenant_shared_domains` for pilot tenants.
- Add content APIs for admin and runtime read.
- Add role/department/qualification filters.
- Add seed importer for Markdown SOPs.
- Ensure runtime only reads published content.

### Slice E - Companion Agent

- Add a `knowledge_companion` Agent with a narrow policy and optional
  `vertical_profile: healthcare_ops` for the pilot.
- Allow only approved low-risk knowledge/training tools.
- Default RAG search to `tenant_knowledge` only; optional `agentlayer_docs` when
  platform help is explicitly needed (see **RAG Domain Model And Search Policy**).
- Require source citation and content version in answers.
- Force escalation for blocked query patterns defined by `vertical_profile` (e.g.
  PHI deny in `healthcare_ops`).
- Add evaluation scenarios; reuse generic search tests across verticals.

### Slice F - Admin UI

- Tenant Admin (see **Tenant Admin Operations**):
  - manage departments and profession roles
  - assign users to roles/departments
  - assign qualifications and expiry dates
  - enable low-risk clinical tools
  - configure `rag_tenant_shared_domains` for clinical pilot
- Clinical Admin:
  - configure content categories
  - configure review/approval workflow
- Content workflow:
  - draft editor
  - reviewer queue
  - approver publish action
  - version diff
- Tool Admin:
  - show tool risk tier and data class
  - enable/disable per tenant, department, role, qualification

### Slice G - Audit And Evaluation

- Add knowledge answer audit:
  - actor
  - tenant
  - role/context
  - content ids and versions
  - tool calls
  - blocked/escalated reasons
  - model profile
- Add evaluation datasets:
  - SOP lookup
  - role filtering
  - blocked query patterns (vertical profile)
  - missing qualification
  - expired content
  - unsupported device
- Add regression checks before publishing prompt/tool policy changes.

### Slice H — Vertical connectors (example: healthcare)

Not part of the core platform. See
[`knowledge-companion/verticals/`](./knowledge-companion/verticals/README.md).

Patient/FHIR gateway: operator-local gated task docs.

### Slice I — Vertical real-time / ML (example: healthcare)

PDMS/ML: local operator-local vertical docs.

## Immediate Next Steps

Recommended next 10 tasks:

1. Keep MVP explicitly free of sensitive context data (define per vertical).
2. Create a first role matrix for your pilot vertical.
3. Create a first qualification matrix.
4. Define the first `tenant_content` schema.
5. Implement Task 02: `knowledge_companion` + `tenant_knowledge`.
6. Pilot interim ingest via Admin UI (Team knowledge section).
7. Add `tenant_knowledge` to `rag_tenant_shared_domains`.
8. Define generic `knowledge.*` tool capabilities.
9. Select 20-50 self-authored pilot documents.
10. Pick vertical profile: `default_ops` or `healthcare_ops` — see [`verticals/`](./knowledge-companion/verticals/README.md).

## Open Questions

- Which vertical profile should ship first (`default_ops` vs `healthcare_ops`)?
- Should profession roles be imported from HR/LDAP or managed in tenant admin UI?
- Should qualifications be platform-wide (recommended) or per-vertical extensions?
- Which `vertical_profile` should be the second pilot (field service, IT ops, …)?
- What is the minimum audit log before any vertical enables live integrations?

Healthcare-specific open questions:
operator-local vertical docs (not published in this repository)
