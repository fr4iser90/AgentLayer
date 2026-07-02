---
doc_id: knowledge-companion-vertical-healthcare-ops
domain: agentlayer_docs
tags: [planning, knowledge-companion, vertical-profile, healthcare]
---

## Vertical profile: `healthcare_ops`

First regulated-industry pilot on the generic
[knowledge companion platform](../knowledge-companion-plan.md). Uses the same
`knowledge_companion` agent, `tenant_knowledge` RAG domain, and `tenant_content`
CMS — plus healthcare-specific policy and connectors.

**Platform tasks 01–06 must be complete before vertical connectors.**

### When to use this profile

- Hospitals, clinics, clinical departments
- Anesthesia, OP, ICU, medtech teams
- Self-authored workflow notes **without PHI** in Phase 1

**Onboarding:** create a live tenant from template `tpl_healthcare_ops` when the
template engine exists (see platform plan — *Tenant Provisioning And Templates*).
For solo dev, one manual tenant with `vertical_profile: healthcare_ops` is enough.

### Configuration

```yaml
knowledge_companion:
  vertical_profile: healthcare_ops
  default_search_domains: [tenant_knowledge]
  block_patient_specific_queries: true
  disclaimer_default: learning_aid_not_official_sop
```

Optional UI alias: display name "Clinical companion" — same agent, no code fork.

### Sample profession roles (tenant-configurable)

- anesthesia nurse, OTA, anesthesiologist, surgeon, ICU nurse
- respiratory therapist, medtech, ward manager, trainee, pool staff

### Sample departments

- anesthesia, surgery, ICU, emergency, medtech, OR areas

### Sample qualifications

- device training (e.g. ventilator), ACLS/PALS, local SOP completion

### Sample content (`content/healthcare-pilot/`)

- tube / circuit change interval reminders
- setup and cleanup checklists
- onboarding notes for common tasks
- material location FAQs
- **No** patient names, case numbers, monitor screenshots, or copied hospital PDFs

## Sensitive data (healthcare)

Anesthesia and OP workflows become high-risk once the system processes **PHI**,
live vitals, medication context, or predictive clinical warnings. Treat as **vertical
tasks H1–H3**, not platform MVP.

Phase 1 (platform + this profile) must avoid:

- patient identifiers and case-specific data
- KIS/PDMS/live device integration
- patient-level FHIR resources
- copied official SOPs / manufacturer manuals / guideline scans

Allowed in Phase 1:

- self-authored team notes and checklists (see platform content boundary)
- generic device reference **without patient context**
- simulated scenarios without identifiers

Before PHI or live clinical data:

- tenant DPA / privacy review
- patient-context audit logging
- read-only integration boundary
- retention and redaction policy
- clinical safety / MDR review where applicable
- incident and escalation runbooks

## Healthcare vertical tasks (gated)

These are **not** part of the core platform backlog (tasks 01–06).

| Task | File | Goal |
|------|------|------|
| H1 | [07-fhir-read-only.md](./healthcare-ops/07-fhir-read-only.md) | FHIR read-only patient context |
| H2 | [08-pdms-devices.md](./healthcare-ops/08-pdms-devices.md) | PDMS / device streams |
| H3 | [09-predictive-ml-voice.md](./healthcare-ops/09-predictive-ml-voice.md) | Predictive ML + voice (OR) |

Entry gate for H1: platform MVP audited, privacy and clinical safety sign-off.

## Healthcare tool capabilities (vertical pack)

Add only after platform `knowledge.*` tools are stable:

- `healthcare.ops.read_schedule`
- `healthcare.fhir.read_patient`
- `healthcare.fhir.read_allergy`
- `healthcare.fhir.read_observation`
- `healthcare.devices.read_vitals`
- `healthcare.alerts.notify`

## Evaluation scenarios (healthcare)

- PHI refusal ("Patient Müller allergies?")
- contraindication / escalation when no published hit
- expired qualification blocks content
- source citation includes disclaimer level

## Open questions (healthcare)

- MDR classification threshold for assistive alerts
- minimum audit log before FHIR read
- two-person approval for which content types
- jurisdiction-specific deployment constraints

## See also

- Platform plan: [`../knowledge-companion-plan.md`](../knowledge-companion-plan.md)
- Platform tasks: [`../README.md`](../README.md)
- Other verticals: [`./README.md`](./README.md)
