---
doc_id: healthcare-task-07-fhir-readonly
domain: agentlayer_docs
tags: [healthcare, task, fhir, patient-data]
status: pending
---

## Task 07 — FHIR read-only (gated)

**Status:** pending  
**Depends on:** Platform [task 06](../06-review-approval-workflow.md) + privacy gate  
**Goal:** Read-only patient context from FHIR for scoped clinical answers — **not**
before Phase 1 MVP is stable and approvals exist.

### Entry gate (must be documented and signed off)

- [ ] Tenant DPA / privacy review completed
- [ ] Clinical safety review completed
- [ ] Patient-context audit logging designed and implemented
- [ ] Incident and escalation runbook exists
- [ ] Deny-by-default patient data policy tested

### Scope

- [ ] FHIR connector config per tenant (base URL, credentials via secrets)
- [ ] Read resources: Patient, Encounter, AllergyIntolerance, Observation,
      MedicationRequest (read-only)
- [ ] Tools: `clinical_fhir.read_*` capabilities with risk tier **restricted**
- [ ] Clinical context capsule assembly (no raw dump into prompt)
- [ ] Source attribution per patient-derived fact
- [ ] Retention / redaction policy for cached FHIR payloads (prefer no cache MVP)
- [ ] `knowledge_companion` escalation when FHIR unavailable or unauthorized

### Out of scope

- Writeback to KIS
- PDMS live streams
- Predictive alerts from vitals

### Acceptance criteria

- [ ] Authorized role with active encounter can ask allergy question with cited FHIR source.
- [ ] User without patient context gets refusal, not hallucination.
- [ ] All FHIR tool calls appear in audit log.
- [ ] Synthetic/sandbox FHIR fixtures for tests (no real PHI in CI).

### Next task

→ [08 — PDMS and devices](./08-pdms-devices.md)
