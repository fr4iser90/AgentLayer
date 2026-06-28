---
doc_id: planning-healthcare-clinical-companion
domain: agentlayer_docs
tags: [planning, healthcare, clinical-companion, tenants, governance, cms]
---

## Purpose

This document captures the first strategy, roadmap, drift analysis, and
implementation plan for a healthcare "clinical companion" on top of AgentLayer.
It is intentionally a planning document, not an ADR. Promote specific decisions
to ADRs only when a slice is ready to implement or locks a security, tenancy, or
clinical safety boundary.

The near-term plan is simple: start with a governed, tenant-scoped clinical
knowledge companion that does not process real patient data. The long-term goal
still includes anesthesia and operating-room workflows, but those workflows
must be reached through explicit safety, privacy, certification, and audit
gates.

## North Star

The clinical companion is a universal role-aware interface for hospital staff.
It should recognize who is using it, which tenant and department they belong to,
which clinical context is active, and which content, tools, and recommendations
are allowed.

The companion should answer from approved clinical content, explain its sources,
show the active content version, and escalate when the request needs patient
data, a missing qualification, or a human decision.

The CMS is the controlled clinical knowledge base. It stores SOPs, checklists,
drug information, device manuals, onboarding paths, emergency algorithms, and
role-specific summaries with draft/review/publish workflows.

## Sensitive Data Strategy

Anesthesia and OP workflows become difficult as soon as the system processes
patient data, real-time vital signs, medication context, or predictive warnings.
Treat these as later phases.

Phase 1 should avoid PHI/PII and should not connect to KIS, PDMS, live medical
devices, or patient-level FHIR resources. It may use:

- approved SOPs and checklists
- device manuals without patient context
- generic medication reference content, if approved by clinical governance
- onboarding material
- role-specific training material
- simulated or synthetic clinical examples

Patient data should only enter after these controls exist:

- tenant-specific DPA/privacy review
- role and context authorization
- patient-context audit logging
- source attribution for every patient-derived fact
- read-only integration boundary
- retention and redaction policy
- clinical safety classification and MDR review
- incident and escalation runbooks

Predictive ML from real-time device data is a later high-risk capability. It
should start as offline simulation/evaluation, then shadow mode, then supervised
assistive alerts only after evidence and governance gates are met.

## Self-Authored MVP Content Boundary

The safest first MVP content should be self-authored operational knowledge, not
copied clinical or manufacturer documents. The system can make these notes
searchable through RAG as long as they are clearly labeled, versioned, and kept
out of patient context.

Allowed MVP examples:

- self-written workflow notes
- self-written setup and cleanup checklists
- self-written tube, filter, circuit, or device change interval reminders
- self-written onboarding notes for common tasks
- self-written FAQs for local material locations and preparation steps
- simulated scenarios without patient identifiers

Avoid in the MVP:

- scanned SOPs, copied clinic documents, or copied guideline text
- copied manufacturer manuals, tables, images, diagrams, or PDFs
- screenshots from KIS, PDMS, monitors, device logs, or patient charts
- patient names, case numbers, dates of birth, room numbers tied to patients, or
  other identifiers
- real medication plans, lab results, vital signs, notes, or case histories
- claims that the content is an official SOP unless it was formally approved by
  the responsible organization

Every MVP content item should show:

- author
- tenant
- version
- created and updated date
- status: personal note, team draft, reviewed, approved, or published
- source type: self-authored, imported with permission, or external reference
- disclaimer level: learning aid, local draft, approved clinical content

The companion should answer from self-authored MVP content as an orientation or
learning aid. It should not present that content as an official clinical order,
patient-specific recommendation, or replacement for approved SOPs, manufacturer
instructions, or local policy.

## Current AgentLayer Baseline

AgentLayer already has several platform concepts that map well to the clinical
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

This means the healthcare companion should extend existing governance patterns
instead of inventing a separate clinical runtime.

## Current Drifts And Gaps

The current platform is a generic agent runtime, not yet a clinical system.
The main drifts from the healthcare target are:

- Identity is still too simple for clinical authorization. Current user roles
  are close to `admin`/`user`; clinical use needs profession, department,
  location, active shift, qualifications, and certifications.
- Tool policy is tenant-aware but not yet clinical-context-aware. Healthcare
  tools need role, department, location, patient-context, and certification
  checks.
- There is no clinical CMS domain yet. Current RAG/knowledge primitives need a
  controlled editorial model with draft/review/publish, expiry, source, and
  clinical owner metadata.
- There are no healthcare connectors yet. FHIR, HL7 v2, OP scheduling, PDMS,
  DICOMweb, SDC/IEEE 11073, and device streams should be modeled as future
  connector domains.
- Audit exists as a platform direction, but clinical audit needs stronger
  structure: who asked, which patient/context was active, which source version
  was used, which tool ran, and whether the answer was advisory or blocked.
- The current tool capability model is a good base, but clinical tools need a
  risk tier and safety class in addition to `domain.action`.
- Agent evaluation exists for model/tool behavior, but clinical content quality,
  hallucination risk, contraindication handling, and escalation behavior need
  dedicated evaluation scenarios.
- Documentation paths still contain some historical references to `src/...`
  while the active backend paths are under `apps/backend/...`. New healthcare
  docs should cite current paths and avoid reviving old layout names.

## Tenant Model

Each hospital, clinic group, or isolated deployment should be a tenant. A tenant
owns its clinical content, users, integrations, policies, audit logs, and tool
configuration.

Recommended tenant-level objects:

- tenant profile: name, region, data residency, enabled features
- departments: anesthesia, surgery, ICU, emergency, medtech, nursing, etc.
- locations: hospital site, OR area, ward, device pool
- professions: anesthesia nurse, OTA, surgeon, anesthesiologist, ICU nurse
- qualifications: ACLS, PALS, device training, medication privileges, local SOP
  training, onboarding level
- content collections: SOPs, checklists, emergency algorithms, manuals
- tool policies: which tools are enabled for which roles and contexts
- integration configs: SSO, LDAP/HR, CMS import, FHIR endpoint, OP plan
- governance workflows: reviewer groups, approvers, expiry policy

Tenant admins are required. Without tenant admins, hospitals cannot safely
configure departments, staff roles, content ownership, device qualifications,
and local SOP validity.

## Role And Permission Model

Use a combined RBAC/ABAC model.

RBAC answers: what role does the user have?

ABAC answers: under which attributes may that role act?

Context-based policy answers: is the current situation valid for this action?

Core global roles:

- Platform Owner: manages platform-level defaults and tenant lifecycle.
- Global Security Admin: manages global security policy and incident controls.
- Global Compliance Auditor: reviews cross-tenant compliance metadata without
  access to tenant PHI by default.
- Integration Engineer: manages connector templates and technical onboarding.
- Model Governance Admin: manages model profiles, prompt governance, and
  evaluation promotion gates.

Core tenant roles:

- Tenant Admin: manages users, departments, tenant policies, and feature flags.
- Clinical Admin: manages clinical workflow configuration and role mappings.
- Content Editor: writes content drafts but cannot publish.
- Content Reviewer: performs clinical review.
- Content Approver: publishes approved content.
- Department Admin: manages department-scoped users, collections, and local SOPs.
- Tool Admin: activates tools per role, department, and risk level.
- Audit Viewer: reads tenant audit logs and reports.
- End User: uses the companion according to role, context, and qualifications.

Clinical end-user roles should be tenant-configurable. Initial examples:

- anesthesia nurse
- OTA
- anesthesiologist
- surgeon
- ICU nurse
- respiratory therapist
- medtech
- ward manager
- trainee
- pool staff

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
and capability gates. Healthcare adds clinical metadata.

Recommended healthcare tool metadata:

- `TOOL_DOMAIN`: `clinical_cms`, `clinical_fhir`, `clinical_ops`,
  `clinical_devices`, `clinical_alerts`, `clinical_training`
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

Example capability strings:

- `clinical_cms.search`
- `clinical_cms.read_approved`
- `clinical_cms.publish`
- `clinical_training.read`
- `clinical_training.verify_qualification`
- `clinical_ops.read_schedule`
- `clinical_fhir.read_patient`
- `clinical_fhir.read_allergy`
- `clinical_fhir.read_observation`
- `clinical_devices.read_vitals`
- `clinical_alerts.notify`

Initial phase should only enable low-risk tools:

- `clinical_cms.search`
- `clinical_cms.read_approved`
- `clinical_training.read`
- `clinical_training.verify_qualification`

Do not enable patient, device, notification, or write tools in the first MVP.

## CMS Strategy

The CMS should be a tenant-scoped clinical content service. It can later connect
to RAG/vector search, but its canonical content model must remain structured and
auditable.

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
- clinical owner
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

## Phased Roadmap

### Phase 0 - Discovery And Safety Framing

Goal: define a simple, safe pilot without patient data.

Deliverables:

- confirm first tenant and first department
- choose two initial roles, for example anesthesia nursing and OTA
- collect 20-50 non-patient SOP/checklist/device/onboarding documents
- define content workflow and clinical owner model
- define tenant roles and admin permissions
- define initial tool capabilities and data classes
- create risk register and privacy assumptions
- document what is explicitly out of scope

Exit criteria:

- no PHI in MVP scope
- first content schema approved
- first role/qualification model approved
- initial safety boundaries documented

### Phase 1 - Clinical Knowledge Companion MVP

Goal: deliver useful role-aware knowledge without patient data.

Scope:

- tenant-scoped CMS content model
- CMS search/read tools
- role-specific content filtering
- qualification-aware filtering
- tenant admin role setup
- content editor/reviewer/approver workflow
- source and version display
- answer audit event
- admin preview of effective role/tool/content policy

Out of scope:

- KIS/FHIR patient data
- PDMS/device streams
- DICOM
- predictive ML
- automated clinical alerts
- writeback to clinical systems

### Phase 2 - Context Without PHI

Goal: add operational context while still avoiding patient data where possible.

Scope:

- OR area, department, shift, and role context
- generic OP schedule categories without patient identifiers, if legally safe
- training and onboarding paths by assignment
- device inventory and device manual linking
- simulation mode for clinical scenarios

Exit criteria:

- context policy can explain why content/tools were shown or blocked
- tenant admins can configure departments, roles, and qualifications

### Phase 3 - Read-Only Patient Context

Goal: introduce patient data carefully and only in read-only mode.

Scope:

- FHIR read connector proof of concept
- Patient, Encounter, AllergyIntolerance, Observation, MedicationRequest
- patient-context audit log
- stricter access controls
- source attribution per patient fact
- redaction and retention policy
- clinical safety review

Entry gate:

- privacy review completed
- clinical safety review completed
- tenant has signed integration and data handling approvals
- audit and incident process tested

### Phase 4 - Real-Time Device And PDMS Context

Goal: add live clinical context with strong safety constraints.

Scope:

- PDMS read connector
- device stream ingestion, likely Kafka/MQTT abstraction
- normalized observations
- alarm/event context
- no autonomous treatment decisions
- shadow evaluation of any predictive model

### Phase 5 - Predictive And Multimodal Assistance

Goal: supervised assistive predictions and voice UI.

Scope:

- speech-to-text and text-to-speech with medical vocabulary evaluation
- predictive model serving in shadow mode
- feedback loop for warnings
- model governance and promotion criteria
- supervised alerts with human confirmation

## Complex Implementation Plan

### Slice A - Planning Artifacts

- Create this planning document.
- Add a healthcare section to the docs index.
- Draft future ADR candidates:
  - clinical tenant authorization model
  - clinical content status and publication model
  - healthcare tool risk tiers
  - patient data boundary and audit model

### Slice B - Domain Model Design

- Add conceptual domain objects for:
  - ClinicalTenantProfile
  - Department
  - ClinicalRole
  - Qualification
  - ClinicalContent
  - ContentVersion
  - ContentApproval
  - ClinicalToolPolicy
  - ClinicalContext
  - ClinicalAuditEvent
- Keep these separate from existing simple `User.role` until a migration plan is
  ready.
- Decide whether clinical roles are stored as identity attributes, tenant policy
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

- Implement tenant-scoped clinical content tables.
- Add draft/review/publish states.
- Add version history and source references.
- Add content-origin metadata for self-authored, permissioned import, and
  external reference content.
- Add an MVP ingestion rule that rejects copied official documents, scans,
  patient screenshots, and patient identifiers by default.
- Add content APIs for admin and runtime read.
- Add role/department/qualification filters.
- Add seed importer for Markdown SOPs.
- Ensure runtime only reads published content.

### Slice E - Companion Agent

- Add a `clinical_companion` Agent with a narrow policy.
- Allow only approved low-risk CMS/training tools.
- Require source citation and content version in answers.
- Force escalation when user asks for patient-specific advice in Phase 1.
- Add clinical prompt evaluation scenarios.

### Slice F - Admin UI

- Tenant Admin:
  - manage departments and clinical roles
  - assign users to roles/departments
  - assign qualifications and expiry dates
  - enable low-risk clinical tools
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

- Add clinical answer audit:
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
  - contraindicated patient-specific request in Phase 1
  - missing qualification
  - expired content
  - unsupported device
- Add regression checks before publishing prompt/tool policy changes.

### Slice H - Patient Data Gateway

Only start after Phase 1 is useful and audited.

- Define FHIR connector boundaries.
- Use read-only service credentials.
- Map FHIR resources to a normalized clinical context capsule.
- Do not store raw patient payloads unless explicitly approved.
- Add patient-context audit and redaction.
- Add deny-by-default patient data policy.
- Add sandbox and synthetic patient fixtures.

### Slice I - Real-Time And ML Gateway

Only start after patient data governance is proven.

- Build stream ingestion abstraction.
- Normalize device observations.
- Add shadow-mode ML evaluation.
- Add warning calibration and false-positive tracking.
- Require human confirmation and escalation rules.

## Immediate Next Steps

Recommended next 10 tasks:

1. Keep MVP explicitly non-PHI and document that boundary in product language.
2. Create a first role matrix for anesthesia nursing and OTA.
3. Create a first qualification matrix for device training, emergency training,
   and local SOP completion.
4. Define the first clinical content schema.
5. Define the first CMS publication workflow.
6. Define clinical tool metadata extensions.
7. Define a deny-by-default policy for patient-specific questions in Phase 1.
8. Select a pilot content pack with 20-50 documents.
9. Add clinical evaluation scenarios for role filtering and escalation.
10. Decide which future decision needs the first ADR.

## Open Questions

- Should clinical roles be imported from HR/LDAP claims or managed inside the
  tenant admin UI first?
- Should qualifications be a general identity concept or a healthcare-only
  extension?
- Who is legally responsible for content approval inside a tenant?
- Which content types require two-person approval?
- Which tenant roles may see draft clinical content?
- Should the first CMS be built inside AgentLayer or integrated from an external
  headless CMS?
- Which jurisdictions and regulations define the first deployment target?
- At what point does the companion become regulated medical device software?
- What is the minimum audit log needed before patient data is allowed?
- Which clinical claims are forbidden until MDR/privacy review is complete?
