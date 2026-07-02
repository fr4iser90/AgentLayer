---
doc_id: healthcare-task-09-predictive-ml-voice
domain: agentlayer_docs
tags: [healthcare, task, ml, voice]
status: pending
---

## Task 09 — Predictive ML and voice (gated)

**Status:** pending  
**Depends on:** [08](./08-pdms-devices.md)  
**Goal:** Supervised assistive predictions and multimodal interaction — highest
clinical and regulatory risk; last in roadmap.

### Entry gate

- [ ] Shadow-mode evaluation dataset and false-positive tracking
- [ ] Model governance process (promotion criteria, rollback)
- [ ] Clinical sign-off for assistive (not autonomous) alerts
- [ ] MDR assessment for predictive features

### Scope

- [ ] Model serving interface (gRPC/REST) with tenant policy
- [ ] Shadow predictions logged but not shown to users initially
- [ ] Supervised alerts with human confirmation requirement
- [ ] Feedback loop: was warning correct?
- [ ] STT/TTS with medical vocabulary evaluation
- [ ] Voice UI for hands-busy scenarios (OR) — optional pilot

### Out of scope

- Fully autonomous closed-loop control
- Unsupervised auto-notification to pagers without policy

### Acceptance criteria

- [ ] Shadow mode runs without user-facing alerts until promotion gate passed.
- [ ] Promoted alert includes confidence, source signals, and escalation path.
- [ ] Voice path meets latency and privacy requirements for tenant policy.

### End of healthcare vertical roadmap

Further healthcare tasks (CDS Hooks, KIS embed) should be added under
`verticals/healthcare-ops/` after H1–H3 gates pass.
