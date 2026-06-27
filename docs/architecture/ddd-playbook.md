---
doc_id: ddd-playbook
domain: agentlayer_docs
tags: [architecture, ddd, playbook]
---

## Purpose

This playbook is the day-to-day rulebook for keeping AgentLayer's backend in a
professional DDD shape. It complements `ddd-architecture-map.md` and
`ddd-checklist.md`.

## Dependency Rule

Use this direction by default:

```text
api -> application -> domain
application -> infrastructure adapters
infrastructure -> domain/application ports
domain -> domain only
```

The API layer is transport code. It should not import persistence adapters,
provider clients, catalog clients, settings stores, or external HTTP helpers
directly.

## Where Code Goes

- `api/`: FastAPI routers, request authentication gate, transport-specific
  request/response mapping.
- `application/`: commands, queries, DTOs, use cases, anti-corruption adapters
  that normalize infrastructure concerns for a use case.
- `domain/`: entities, value objects, aggregates, policies, repository
  protocols, and pure business decisions.
- `infrastructure/`: Postgres, provider clients, env/catalog readers, filesystem
  adapters, queues, runtime services, external HTTP.

## Anti-Corruption Layer Rule

Create an application ACL/use-case module when an API endpoint needs any of
these:

- DB rows or persistence stores.
- Provider catalog or provider endpoint clients.
- Env-provider parsing.
- HTTP calls to external providers.
- Cache invalidation for infrastructure adapters.
- Operator settings persistence.

Example:

```text
api/providers/controllers/provider_endpoints_api.py
  -> application/providers/use_cases/provider_admin_acl.py
    -> infrastructure/providers/*
    -> infrastructure/voice/*
    -> infrastructure/settings/*
    -> infrastructure/db/*
```

Do not put this in the controller:

```python
from apps.backend.infrastructure.voice.voice_catalog_providers import ...
```

Use an application use case or ACL function instead.

## Check Policy

- Domain layer violations are hard failures.
- Provider API controllers must not import `apps.backend.infrastructure` at all.
- Global API-to-Infrastructure imports are reported as DDD drift while legacy
  controllers are migrated context by context.
- Once a controller package is migrated, add a strict layer rule for that
  package so regressions fail precommit.

## Migration Workflow

1. Pick one bounded context or controller package.
2. Move orchestration from API into `application/<context>/use_cases/`.
3. Keep request/response mapping in API.
4. Move infrastructure calls behind application functions or ports.
5. Add or tighten a DDD layer rule for that package.
6. Run `python3 scripts/checks/run.py --profile precommit`.

## Review Checklist

- Does API import only `application`, `domain` DTOs/types if needed, and FastAPI?
- Does Application own the workflow?
- Does Domain stay free of DB, FastAPI, provider clients, env, filesystem, and
  runtime side effects?
- Are provider-specific quirks isolated in Infrastructure or an Application ACL?
- Did the DDD check catch the rule you expect it to catch?
