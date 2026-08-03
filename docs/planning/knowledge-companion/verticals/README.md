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
| `healthcare_ops` | regulated / care-ops tenants | operator-local only (not published here) | 01–06 + local extras |
| `field_service_ops` | technicians, maintenance | _(stub — add when needed)_ | 01–06 |
| `it_ops` | internal IT / support | _(stub — add when needed)_ | 01–06 |

### Adding a new vertical

1. Keep sensitive vertical planning **out of the public repository**.
2. Define: sensitive data rules, disclaimer text, blocked patterns, connectors.
3. Seed/demo content for private verticals stays on the operator machine / tenant DB.
4. Do **not** fork `knowledge_companion` or `tenant_knowledge` unless an ADR
   requires it.

### Tenant templates vs vertical profiles

| | Vertical profile | Tenant template |
|---|----------------|-----------------|
| **What** | policy pack (prompts, blocks, connectors) | blueprint to spawn a new tenant |
| **Scope** | reused across many tenants | copied once per new tenant |
| **Example** | `healthcare_ops` policy flags | `tpl_healthcare_ops` → new tenant |

See **Tenant Provisioning And Templates** in
[`../knowledge-companion-plan.md`](../knowledge-companion-plan.md).

Detailed per-vertical product plans are **not** maintained in this public tree.
