---
doc_id: ddd-checklist
domain: agentlayer_docs
tags: [architecture, ddd, checklist, checks]
---

## Purpose

This checklist defines what "DDD-compliant" means for AgentLayer and which
parts are enforced automatically by repository checks.

DDD is not satisfied by moving files into folders. The goal is explicit
bounded contexts, correct dependency direction, honest tactical models, and
application use cases that own orchestration.

## Automated Checks

Run:

```bash
python3 scripts/checks/run.py --profile architecture
python3 scripts/checks/run.py --profile precommit
python3 scripts/checks/run.py --profile ci
```

### `ddd_layers`

- [x] Checks are AST-based, not grep-based.
- [x] Checks are configured in `scripts/checks/config.json`.
- [x] Checks are layer-wide, not hardcoded to Domain only.
- [x] Domain must not import API, dashboard, infrastructure, integrations, or media.
- [x] Application imports of API, dashboard, or integrations are scanned and
  reported as migration drift.
- [x] API imports of dashboard, integrations, or infrastructure are scanned and
  reported as migration drift.
- [x] Provider API controllers enforce no direct `apps.backend.infrastructure`
  imports; provider DB/catalog/env/voice access must go through
  `application/providers/use_cases/`.
- [x] Infrastructure imports of API or dashboard are scanned and reported as
  migration drift.
- [x] Rules support `enforce: true|false`, so hard invariants and advisory
  migration reports are explicit in config.
- [x] `ddd_layers` runs on staged/changed files.
- [x] `ddd_layers_all` runs on all backend Python files in CI.
- [x] `ddd_layers_report` prints architecture drift summaries.

### `ddd_quality`

- [x] Domain root must contain bounded-context folders, not Python modules.
- [x] Application contexts must expose the CQRS/use-case skeleton:
  `ports.py`, `commands/`, `queries/`, `dtos/`, `use_cases/`.
- [x] Empty tactical placeholders such as fake `entities.py`,
  `aggregates.py`, `repositories.py`, `schemas.py`, `value_objects.py`, or
  `policies.py` fail the check.
- [x] Domain contexts must expose `entities.py`, `repositories.py`,
  `schemas.py`, and `value_objects.py`.
- [x] Large Domain/Application files are reported so God files stay visible.
- [x] Large-file reporting is advisory until the current migration hotspots are
  split; then it should become a hard failure threshold.

## Layer Rules

### API

- [ ] API modules only translate transport input/output.
- [ ] API modules call Application commands/queries.
- [x] Migrated Provider API modules call Application provider use cases/ACLs
  instead of Infrastructure adapters directly.
- [ ] API modules do not own business workflows.
- [ ] API modules do not call Domain internals for orchestration.

### Application

- [ ] Application owns use-case orchestration.
- [ ] Application commands mutate state.
- [ ] Application queries read state.
- [ ] Application DTOs define use-case boundaries.
- [ ] Application ports define required external capabilities.
- [ ] Application coordinates Domain rules and Infrastructure adapters.

### Domain

- [x] Domain root is context-only.
- [x] Domain imports no API/dashboard/infrastructure/integration/media code.
- [ ] Domain modules contain rules, policies, invariants, and pure decisions.
- [ ] Domain does not orchestrate provider calls, DB transactions, or websocket
  side effects.
- [x] Domain tactical files exist only when they contain real model behavior.

### Infrastructure

- [ ] Infrastructure implements adapters for persistence, provider clients,
  runtime services, queues, and file systems.
- [ ] Infrastructure may call Domain/Application ports.
- [ ] Infrastructure must not import API routers or dashboard modules.

## Tactical DDD Rules

Use tactical files only when they carry real meaning:

- [ ] `entities.py`: identity and lifecycle behavior.
- [ ] `aggregates.py`: consistency boundaries and invariant enforcement.
- [ ] `value_objects.py`: immutable validated concepts.
- [ ] `policies.py`: domain decisions that can be tested without IO.
- [ ] `repositories.py`: protocols for aggregate persistence.
- [ ] `events.py`: facts emitted by Domain behavior.
- [ ] `services.py`: stateless domain services for rules that do not belong to
  a single entity.

Do not create tactical files just to satisfy a folder shape. Empty tactical
files are explicitly forbidden by `ddd_quality`.

## Current Migration Status

### Done

- [x] Domain root files moved into bounded contexts.
- [x] Shared identity concerns moved to `apps/backend/domain/shared/`.
- [x] Agent runtime files moved to `apps/backend/domain/agent_runtime/`.
- [x] All configured Domain contexts expose real entities, value objects,
  repository protocols, and schema validators.
- [x] Application context folders exist with CQRS/use-case structure.
- [x] All configured Application contexts expose concrete commands, queries,
  DTOs, ports, and use-case functions.
- [x] CVE checks are active in precommit/CI profiles.
- [x] `ddd_layers_all` passes.
- [x] `ddd_quality` is wired into architecture/precommit/CI profiles.

### Not Done

- [ ] Promote Application/API/Infrastructure advisory layer rules to hard
  failures after one full CI run confirms the strict rules remain clean.
- [ ] Large API/Infrastructure files still need decomposition into routers,
  adapters, and persistence services.

## Execution Backlog

### Agent Runtime

- [ ] Extract `application/agent_runtime/use_cases/chat_completion.py` as the
  owner of chat-turn orchestration.
- [ ] Extract `application/agent_runtime/use_cases/tool_execution_loop.py` for
  LLM retry, permission ask, tool execution, side effects, and final response
  handling.
- [ ] Extract `application/agent_runtime/use_cases/embedded_subagent.py` for
  embedded subagent orchestration and run persistence.
- [ ] Split pure tool parsing into `domain/agent_runtime/tool_call_parsing.py`.
- [ ] Split tool schema and argument validation into
  `domain/agent_runtime/tool_schema.py`.
- [ ] Move ranking/pinning/forwarding helpers toward
  `domain/tools/forward_policy.py` or a dedicated
  `domain/agent_runtime/tool_forwarding.py`.
- [ ] Split loop guards, recap builders, and transcript helpers into
  `domain/agent_runtime/loop_guards.py` and
  `domain/agent_runtime/tool_transcript.py`.
- [ ] Replace `import *` in `agent_runtime/planner.py` with explicit imports
  before or during the split.
- [x] Remove legacy `agent_runtime/planner.py` compatibility path; chat
  completion now enters through the Application use case.

### Other Contexts

- [ ] Split `plugin_system/registry.py` into discovery, manifest parsing,
  router catalog, and registry aggregate/facade modules.
- [ ] Split `setup/catalog.py` into setup value objects, policies, catalog
  queries, and setup use cases.
- [ ] Split `setup/instance.py` into instance commands, setup status policies,
  token/password/email rules, and infrastructure adapters.
- [ ] Move ComfyUI HTTP calls out of `studio/jobs.py` into Infrastructure and
  keep workflow mutation/checkpoint rules in Domain.
- [ ] Split `delegation/enforcement.py` into artifact scope, enforcement
  policies, handoff/orchestrator policy, and result display helpers.
- [ ] Split `rag/ingest_common.py` into fingerprint value objects, ingest
  decision policies, and ingest summary entities.
- [ ] Split `model_routing/smart_route.py` into route policies, classifier
  result value objects, and router-call service/facade.

### Tactical Models Added

- [x] `domain/collections`: entities, value objects, repository ports, and
  collection persistence port registry exist.
- [x] `domain/dashboards`: dashboard aggregate, access grant, value objects,
  repository ports, and layout/data schema validators exist.
- [x] `application/dashboards`: commands, queries, DTOs, ports, and use cases
  exist and use dashboard repository ports.
- [x] `infrastructure/persistence/postgres/dashboard_repository.py`: Postgres
  adapter implements dashboard repository ports.
- [x] `domain/identity`: user/tenant entities, value objects, repository ports,
  and identity validators exist.
- [x] `application/identity`: commands, queries, DTOs, ports, and use cases
  exist and use identity repository ports.
- [x] `infrastructure/persistence/postgres/identity_repository.py`: Postgres
  adapters implement user and tenant repository ports.
- [x] `domain/providers`: provider endpoint aggregate, model catalog preference,
  value objects, repository ports, and provider schema validators exist.
- [x] `application/providers`: commands, queries, DTOs, ports, and use cases
  exist for endpoint and model catalog preference workflows.
- [x] `infrastructure/persistence/postgres/provider_repository.py`: Postgres
  adapters implement provider endpoint and catalog preference repository ports.
- [x] `domain/agent_runtime`, `delegation`, `model_routing`, `plugin_system`,
  `rag`, `scheduling`, `setup`, `shares`, `studio`, `tools`, `voice`, and
  `workspace`: entities, value objects, repository ports, and schema validators
  exist.
- [x] `application/agent_runtime`, `collections`, `model_routing`, `rag`,
  `setup`, `sharing`, `studio`, `tools`, `voice`, and `workspace`: commands,
  queries, DTOs, ports, and use-case functions exist.

### Layer Drift

- [x] Remove Application -> API/dashboard imports reported by `ddd_layers_all`.
- [x] Remove API -> dashboard/integrations imports reported by `ddd_layers_all`.
- [x] Remove Infrastructure -> API/dashboard imports reported by `ddd_layers_all`.
- [x] Remove `apps/backend/dashboard` compatibility/double-structure Python
  modules; canonical dashboard services now live under API or Infrastructure.
- [ ] Flip Application/API/Infrastructure layer rules from `enforce: false` to
  `enforce: true` after one full CI run confirms zero drift outside the focused
  check.

### Remaining Large Files Outside Domain/Application

- [ ] Split `apps/backend/api/main.py` composition root into router registration,
  auth/session endpoints, lifecycle, and health modules.
- [ ] Split `apps/backend/api/dashboard_api.py` into dashboard commands,
  sharing, media/upload, templates, and proposal routers.
- [ ] Split `apps/backend/api/workspaces_api.py` and
  `apps/backend/api/benchmarks_admin_api.py`.
- [ ] Split `apps/backend/infrastructure/db/db.py`,
  `operator_settings.py`, `dashboard_db.py`, `conversations_db.py`,
  `workspace_service.py`, and related large Infrastructure services.

## Definition Of Done

- [x] `PYTHONPATH=scripts/checks python3 scripts/checks/run.py --check ddd_layers_all --check ddd_quality` passes.
- [x] `python3 scripts/checks/run.py --profile precommit` passes.
- [x] `python3 scripts/checks/run.py --profile ci` passes.
- [x] No Domain root Python modules exist.
- [x] No empty tactical DDD placeholder files exist.
- [x] No new cross-layer imports are introduced.
- [x] No large Domain/Application files remain.
- [ ] Large API/Infrastructure files have an owner and a split plan.
- [x] New features enter through Application commands/queries, not Domain
  orchestration files.
