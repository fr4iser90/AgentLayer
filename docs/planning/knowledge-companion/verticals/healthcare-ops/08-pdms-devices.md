---
doc_id: healthcare-task-08-pdms-devices
domain: agentlayer_docs
tags: [healthcare, task, pdms, devices]
status: pending
---

## Task 08 — PDMS and devices (gated)

**Status:** pending  
**Depends on:** [07](./07-fhir-read-only.md)  
**Goal:** Real-time device / PDMS **read** context for situational awareness —
still no autonomous treatment decisions.

### Entry gate

- [ ] Task 07 audit and privacy controls proven in pilot
- [ ] Device data classification and retention approved
- [ ] MDR / clinical risk classification updated for live monitoring features

### Scope

- [ ] PDMS read connector (tenant-configured)
- [ ] Stream ingestion abstraction (Kafka/MQTT or adapter interface)
- [ ] Normalize observations (vitals, ventilator parameters)
- [ ] Tools: `clinical_devices.read_vitals` with strict role + context gates
- [ ] Alarm/event context for companion (explain, do not auto-treat)
- [ ] Shadow mode only for any anomaly hints

### Out of scope

- Autonomous medication or ventilator changes
- Predictive ML production alerts (task 09)

### Acceptance criteria

- [ ] Companion can explain current monitored values when authorized and in context.
- [ ] Unauthorized or out-of-context requests denied with audit entry.
- [ ] Load and failure modes documented (connector down → safe degradation).

### Next task

→ [09 — Predictive ML and voice](./09-predictive-ml-voice.md)
