---
doc_id: knowledge-companion-verticals
domain: agentlayer_docs
tags: [planning, knowledge-companion, vertical-profile]
---

## Vertical profiles

The **knowledge companion platform** (tasks 01–06) is industry- and
profession-agnostic. A **vertical profile** adds:

- prompt rules and disclaimers
- blocked query patterns (e.g. PHI, customer PII)
- optional connector packs (FHIR, CRM, ticketing, IoT)
- evaluation scenarios
- sample content paths

Platform code uses generic ids: `knowledge_companion`, `tenant_knowledge`,
`tenant_content`, `profession_role`. Vertical behavior is configuration.

### Available / planned profiles

| Profile id | Domain | Doc | Platform tasks required |
|------------|--------|-----|-------------------------|
| `default_ops` | any team / internal ops | use platform plan only | 01–06 |
| `healthcare_ops` | hospitals, clinical teams | [healthcare-ops.md](./healthcare-ops.md) | 01–06 + vertical H1–H3 |
| `field_service_ops` | technicians, maintenance | _(stub — add when needed)_ | 01–06 |
| `it_ops` | internal IT / support | _(stub — add when needed)_ | 01–06 |

### Adding a new vertical

1. Copy the structure of `healthcare-ops.md`.
2. Define: sensitive data rules, disclaimer text, blocked patterns, connectors.
3. Add sample content under `content/<vertical>-pilot/`.
4. Do **not** fork `knowledge_companion` or `tenant_knowledge` unless an ADR
   requires it.

### Tenant templates vs vertical profiles

| | Vertical profile | Tenant template |
|---|----------------|-----------------|
| **What** | policy pack (prompts, blocks, connectors) | blueprint to spawn a new tenant |
| **Scope** | reused across many tenants | copied once per new tenant |
| **Example** | `healthcare_ops` PHI rules | `tpl_healthcare_ops` → new tenant "klinik-pilot" |

See **Tenant Provisioning And Templates** in
[`../knowledge-companion-plan.md`](../knowledge-companion-plan.md).

### Healthcare-only gated tasks

Regulated clinical connectors live under
[`healthcare-ops/`](./healthcare-ops/) — not in the core platform backlog.
