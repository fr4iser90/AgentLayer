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

### `tenant_scope`

- [x] Checks are AST-based, verb-anchored (`FROM t` / `UPDATE t SET` /
  `DELETE FROM t`), so prose that mentions a table name does not fire.
- [x] A statement against a configured tenant-scoped table must filter on
  `tenant_id`, or carry a marker on its own line, the line above, or anywhere
  inside the enclosing function:
  - `# tenant-scope: site-wide` — genuinely cross-tenant (login lookup by
    email, canonical user fetch by primary key, bootstrap admin lookup).
  - `# tenant-scope: guarded <what>` — tenancy is enforced in Python rather
    than in the WHERE clause, e.g. by an `AdminScope` check earlier in the
    handler. Naming the guard keeps the exemption reviewable.
- [x] f-strings are treated as leaves, so interpolated fragments are not
  double-counted.
- [x] Statements whose filter is not statically visible (f-string clause,
  concatenation cut off at `WHERE`/`SET`) are reported as *unresolved* and do
  not fail a staged run — a gate that cries wolf gets switched off.
- [x] `tenant_scope` runs on staged/changed files in fast/precommit/CI.
- [x] `tenant_scope_all` runs report-only across the tree in
  architecture/security.
- [x] Table list is configured in `scripts/checks/config.json`
  (`tenant_scoped_tables`), migrations excluded.

## Tenancy Conventions

Decided in [ADR 0012](../adr/0012-admin-tenant-scope.md).

**Data access.** New queries build their tenant filter from
`domain/identity/tenant_scope.py` rather than interpolating a bare
`user_tenant_id()`:

```python
where, params = TenantScope.of(tenant_id).where()   # ("tenant_id = %s", (7,))
scope.require_matches(row)                          # post-read guard
```

`require_matches` raises when a loaded row carries no `tenant_id` or belongs to
another tenant. Use it after a read whose filter came from somewhere else.

**Admin endpoints.** Three concepts, and the wrong guard silently grants too much:

| Guard | Use for |
| --- | --- |
| `require_admin_capability(request, slug)` | Tenant-free reads — catalogs, definitions, metadata. |
| `require_admin_scope(request, slug)` | Anything that names a **target**: a user, a tenant, a policy row, a grant. |
| `require_site_admin(request)` | Instance-level work that must never be delegated — see below. |
| `require_admin(request)` | **Gone.** No call sites remain; it survives only as the `require_site_admin` alias definition. Do not reintroduce it. |

The rule is one line: **if the request names a target, use `require_admin_scope`.**
`AdminScope.tenant_filter()` returns `None` for a site admin (do not filter) and
the caller's tenant set otherwise; `require_tenant()` and `require_site_wide()`
raise `AdminScopeError`, which handlers map to 403.

**Deliberately undelegable — no capability slug exists for these.** Benchmarks
(shared provider compute), the provider/model catalog and the `global`
model-access policy (one change moves every tenant), RAG `ingest-docs`
(caller-supplied server filesystem path), and scheduler job presets (reads the
server plugin directory). If you are tempted to mint a slug for one of them,
the answer is that the surface is not tenant-shaped.

**Deployment mode.** Ask with a predicate, never with a literal.
`operator_settings.has_org_surface()` and `is_single_user()` replace
`deployment_mode() != "multi_tenant"`, and the frontend mirrors them in
`src/auth/deploymentMode.ts`. The bare comparison answers "is this not
multi_tenant" for every mode added later, so a new mode inherits a
neighbour's behaviour by accident — which is exactly how `single_user`
would have left `/org` reachable. `DEPLOYMENT_MODES` in
`domain/setup/instance.py` is the single canonical list; the settings forms,
the patch writer and the API `Literal` all derive from it. See ADR 0012 §10.

**Memberships.** `tenant_memberships` must agree with `users.tenant_id` —
`require_tenant_member` reads one and `resolve_chat_identity` reads the other,
and a disagreement lets a user enter a tenant while writing into another.
`tenant_membership_upsert` enforces this and has no override. Tenant moves go
through `db.move_user_tenant`, which keeps the row in step, never carries the
old role across, and takes the caller's owned workspaces with it —
`project_workspaces.tenant_id` is denormalised from the owner and would
otherwise drift.

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
