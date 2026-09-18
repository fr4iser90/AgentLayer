---
doc_id: adr-0012-admin-tenant-scope
domain: agentlayer_docs
tags: [adr, rbac, tenant, identity, admin-scope, capabilities, membership, multi-tenancy]
---

# ADR 0012: Admin tenant scope, and why identity/membership stays coupled

## Status

**Accepted.** Implemented 2026-09-17, extended the same day by §7–§10 (the rest of the admin
surface, the workspace tenant column, the LLM publish gate, and the `single_user` deployment
mode). `pytest tests/unit` green (1434 passed, 2 skipped), `CHECK_PROFILE=fast` green including
the `tenant_scope` gate. `schema_132`, `schema_133` and `schema_134` applied to the running
instance and verified against `information_schema`.

Supersedes nothing in [ADR 0011](0011-roles-and-agent-access-without-tenancy.md); it closes a
gap that ADR 0011 left open. ADR 0011 decided *which* capabilities exist. This ADR decides
*how far each one reaches*, and records the conditions under which the bigger identity/membership
split (option (c) below) should be taken up.

## Context

ADR 0011 put admin power into `users.capabilities` slugs and drew one hard boundary: a delegated
holder may never touch a `site_admin`. That boundary was real but narrow. Everything a delegated
holder was allowed to do was still **instance-wide**.

Verified against the code before this change:

- `admin_users_api.admin_list_users` returned **every mailbox on the instance** to any
  `user.manage` holder. The docstring said so out loud: *"A delegated `user.manage` holder may
  edit any non-site-admin user."*
- `admin_patch_user` checked only the target's `site_role`. A company-A admin could edit a
  company-B user, and could move that person between tenants.
- `admin_create_user` accepted any `tenant_id`.
- `agent.assign` had the same shape. `POST /v1/admin/agents/access-policy/batch` granted agents
  against **any** `body.user_id` with no tenant check at all.
- Two subtler ones surfaced while reading the stores rather than the handlers:
  `agent_access_policy_store.list_agent_policies` **OR**-joins its filters, so a `user_id` filter
  is not bounded by the `tenant_id` filter — passing `?user_id=<someone else>` returned that
  person's user-scope rows regardless of the tenant filter. And `scope='global'` in
  `agent_access_policies` reaches every tenant, which no delegated holder should be able to write.

Separately, `tenant_memberships` and `users.tenant_id` were free to disagree.
`require_tenant_member` reads the membership row; `resolve_chat_identity` reads
`users.tenant_id`. A membership row for tenant 2 against a user whose home tenant is 1 lets the
user **pass the entry check while every write still lands in tenant 1** — silently. Nothing
prevented that row. `update_user_tenant` made it worse in the opposite direction: it changed
`users.tenant_id` and left the membership row behind, so a moved user lost entry rights in the
new tenant and kept a role in the old one.

The deployment context changed since ADR 0011 was written. The instance is no longer ~10 friends:
the owner is onboarding friends **plus three companies of roughly 50 users each, each with their
own admin**. A delegated company admin is now a real actor with a real neighbour whose data they
must not reach.

Note on the mode: ADR 0011 §4 assumes `deployment_mode = agent_system`. That is not the shipped
default. The column default is `multi_tenant` (`schema_111_identity_roles_deployment_mode.py`),
the reader fallback is `multi_tenant` (`operator_settings_readers.py`), and `.env` carries no
`DEPLOYMENT_MODE` key. The instance runs multi-tenant unless someone sets it. The scoping below
is mode-neutral: it holds in both modes.

## Decision

### 1. Capability says *what*, scope says *where*

`AdminScope` (`domain/access/capabilities.py`) is a frozen value object layered on top of the
capability slug, not a replacement for it:

```python
@dataclass(frozen=True, slots=True)
class AdminScope:
    actor_id: uuid.UUID
    site_wide: bool
    tenant_ids: frozenset[int]
```

`require_admin_scope(request, capability)` in `infrastructure/identity/auth.py` runs
`require_admin_capability` first, then resolves the range: a `site_admin` gets `site_wide=True`
and `tenant_filter() is None` (do not filter); everyone else gets `tenant_ids = {own tenant}`.

Handlers that act on a **target** must use `require_admin_scope`. Handlers that read a
tenant-free catalog may keep `require_admin_capability` — `GET /v1/admin/agents` lists plugin
definitions and has no tenant target, so it stays as is.

This is deliberately a second object rather than a field on the capability check: the two
questions are asked at different points and conflating them is how the original hole stayed open.

### 2. Global agent policy is never a delegated action

`scope='global'` in `agent_access_policies` affects every tenant. Both the PUT and the DELETE
now call `require_site_wide()` for it. A delegated `agent.assign` holder manages their own
tenant's rows and nothing else.

### 3. A membership row must match the home tenant

`tenant_membership_upsert` now reads `users.tenant_id` inside the same transaction and raises if
the requested tenant differs. There is no override parameter — the invariant is unconditional,
and the error message names the operation that should have been used instead.

### 4. A tenant move keeps the membership row and drops the old role

`move_user_tenant` (in `infrastructure/db/identity_tenants.py`, re-exported through `db`) sets
`users.tenant_id`, deletes the user's membership rows in every other tenant, and inserts a
`tenant_member` row in the new one, in one transaction. `auth.update_user_tenant` delegates to
it and holds no SQL of its own.

**The old role is not read, so it cannot follow the person.** A `tenant_owner` of company A who
is moved to company B arrives as `tenant_member`. Owning one company does not grant owning
another; the new role is granted explicitly afterwards. This is a security default, not an
ergonomic one — it means a move is two operations (move, then grant) rather than one.

### 5. Option (c) — identity/membership split — is deferred, not rejected

The "correct" architecture for one person holding several concurrent memberships is to split
`users` (identity) from membership (a many-to-many relation the whole stack reads through a
session-scoped active tenant). That is option (c). It was costed at **17–26 working days**:
181 `user_tenant_id()` call sites, 41 `resolve_chat_identity()` call sites, a token that carries
exactly one `set_identity(tenant_id, user_id)`, and every store query in between.

The owner's answers when asked were: no current trigger ("ich will es möglich haben"), switching
"im laufenden Tag, mehrmals", visibility "strikt getrennt", data "pro Tenant komplett getrennt".
Those answers describe (c) accurately — and they describe a need nobody currently has. The three
companies are three tenants with 50 users each; none of the named users is employed by two of them.

**Decision: do not build (c) now.** Build the scope layer above, which makes the multi-tenant
instance safe to operate, and keep (c) open behind explicit triggers.

**Triggers that reopen this ADR** — any one of them:

1. A real person needs to hold two memberships **at the same time**, not sequentially. A
   secondment, a shared founder, a contractor working for two of the tenant companies.
2. A user has to **switch tenant more than once in a working day** as a normal part of their job,
   rather than as an admin-performed migration.
3. A compliance or contractual requirement appears for **cross-tenant identity** — one verified
   person, several tenancies, auditable as such.
4. Tenant migration stops being exceptional. If moves happen more than roughly monthly, the
   one-at-a-time migration path is the wrong tool and the model should change instead.

**Explicitly not triggers:** wanting multi-membership "in principle"; a user asking for a second
account (that is a migration); a company asking for a sub-brand (that is a new tenant).

If a trigger lands, the entry point is `resolve_chat_identity` and the token's single
`set_identity` — everything else follows from those two. Do not start by adding a
`tenant_memberships.active` column; that shape cannot carry the switch without touching the same
181 call sites anyway.

### 6. New code routes through `TenantScope`, and the gate enforces the old code

`domain/identity/tenant_scope.py` provides the value object for tenant-filtered data access:
`TenantScope.of(tid).where()` → `("tenant_id = %s", (7,))`, plus `require_matches()` as a
post-read guard that raises when a loaded row carries no `tenant_id` or belongs to another tenant.
New queries build their filter from this rather than interpolating a bare `user_tenant_id()`.

`scripts/checks/checks/tenant_scope.py` is the static gate. It is verb-anchored
(`FROM t` / `UPDATE t SET` / `DELETE FROM t`) so prose that mentions a table name does not fire,
and it treats an f-string as a leaf so fragments are not double-counted. A statement against a
tenant-scoped table must either filter on `tenant_id` or carry a marker, on its own line, the
line above, or anywhere in the enclosing function:

- `# tenant-scope: site-wide` — genuinely cross-tenant (login lookup by email, canonical user
  fetch by primary key, bootstrap admin lookup).
- `# tenant-scope: guarded <what>` — tenancy is enforced in Python rather than in the WHERE
  clause, e.g. by an `AdminScope` check earlier in the handler.

The second marker exists because the alternative was lying with the first. `UPDATE users SET
quota = %s WHERE id = %s` inside a handler that already rejected out-of-scope targets is not
site-wide; it is guarded, and naming the guard keeps it reviewable. Statements whose filter the scan
cannot see (f-string interpolation, concatenation cut off at `WHERE`/`SET`) are reported as
*unresolved* and do not fail a staged run — a gate that cries wolf gets switched off.

Baseline at the time of writing: 114 unscoped and 22 unresolved across the whole tree
(`tenant_scope_all`, report-only). The staged variant blocks.

### 7. The rest of the admin surface is split site vs tenant

The first pass covered `user.manage` and `agent.assign`. The remaining admin endpoints were
classified by one question — *does this act on tenant data, or on the instance?* — and each was
given the guard that matches. `require_admin` was found to be a **pure alias** for
`require_site_admin` (`auth.py:416`), so none of these had been leaking; the problem was the
opposite of the one assumed at the start. A delegated company admin could not administer their
own company at all.

**Tenant-delegated** (`require_admin_scope(<capability>)`):

| Surface | Capability | Note |
| --- | --- | --- |
| Agent policies, prompts, `admin_get_agent` | `agent.assign` | first pass |
| Project runs create/list/get | `dashboard.manage` | already tenant-bound via `db.user_tenant_id` |
| Scheduler jobs and runs | `schedule.manage` | |
| Run traces, tool invocations | `observability.read` | `list_tool_invocations` now *requires* `tenant_id` |
| Message feedback | `feedback.read` | |
| RAG ingest (own tenant) | `knowledge.manage` | |
| Workspace reindex | `workspace.manage` | needs §8's column |
| Per-user model access | `user.manage` | target tenant checked against scope |

**Deliberately site-admin only, with no capability slug.** These consume shared instance resources
or read the instance itself, so there is nothing to delegate:

- **Benchmarks** — running one spends shared provider compute.
- **Provider catalog, model catalog, `global` model-access policy** — one change moves the model
  every tenant gets. `require_provider_admin` used to be a bare forward to `require_admin`; it
  now says *site admin* out loud and documents why it is not delegable.
- **`POST /v1/admin/rag/ingest-docs`** — `docs_root` is a caller-supplied path on the server
  filesystem.
- **Scheduler job presets** — lists preset JSON out of the server plugin directory.

Two candidates that a first classification put on the *relax to tenant member* list were moved
back after reading what they actually touch: the presets endpoint reads server files, and project
runs belong behind a capability rather than bare membership.

### 8. `project_workspaces` gets a real `tenant_id`

`project_workspaces` had no tenant column at all, so no workspace admin surface could answer the
scope question from the row it had already fetched. Two ways out were on the table: derive from
`owner_user_id` on every check, or add the column. The column was chosen.

`schema_132` adds `tenant_id BIGINT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE`,
backfilled from the owner's home tenant, with the `NOT NULL` applied only after the backfill so
the FK never validates a NULL. `users.tenant_id` is itself `NOT NULL` and `owner_user_id` is a
`NOT NULL` FK to `users`, so the backfill resolves for every row.

Because the column is denormalised from the owner it can drift, so `move_user_tenant` updates it
in the same transaction as the user row. A test pins that.

This also fixed a live bug found while looking for the column: `fetch_editable_workspace_tenant_name`
selected `tenant_id` from a table that did not have it. Reproduced against the running database —
`ERROR: column "tenant_id" does not exist` — which made `PUT /v1/workspaces/{id}/delegate` fail
with a 500 on every call. The column makes that query valid.

### 9. Publishing a prompt requires an LLM risk assessment

Publish used to check only that the version row existed. It now runs a utility-model assessment of
the prompt text first (`domain/agent_runtime/prompt_risk.py`), on the agreed rules:

- **Assessed at publish**, not at draft. Drafts stay cheap.
- **`high` is a hard block.** A delegated admin gets 403. Only a site admin may pass it, and
  only by supplying a non-empty `override_reason`, stored on the version with `override_by`.
- **Fail-closed.** Provider unreachable, empty reply, unparseable JSON, or an unusable level all
  raise and the publish is refused (503). A missing verdict never reads as a cleared one, and the
  schema default is `'unassessed'` rather than `'low'` for the same reason.

The LLM verdict is authoritative for the level. The project's existing `_RISK_KEYWORDS` heuristic
was deliberately **not** reused as a blocking floor: it matches `secret`, `token`, `delete`,
`shell`, `root` and friends anywhere in the text, which would block a large share of legitimate
agent prompts, including ones that mention those words only to warn against them. The contract
prompt says so explicitly.

`AGENT_PROMPT_RISK_GATE_ENABLED=0` is the kill switch, and it is not a convenience. The provider
concurrency slot is waited on with no deadline (`llm_concurrency._ProviderGate` polls forever, and
`_DEFAULT_MAX_PARALLEL` is 1 for a spec that sets none), so a saturated provider can hold a
publish open indefinitely and the httpx timeout cannot break that wait. Only the flag can.

`schema_133` adds `risk_level`, `risk_reasons`, `assessed_at`, `override_by`, `override_reason`.
The assessment runs off the event loop via `asyncio.to_thread` — the whole publish chain below
the handler is synchronous, and the default provider timeout is 120 s.

## §10 — `single_user` as a third deployment mode

`deployment_mode` originally carried exactly two values, and the `schema_111` column comment is
authoritative about what they meant: `agent_system` = *single team (no /org UI)*,
`multi_tenant` = *organizations product*. Neither was a user-count axis — both support any number
of accounts. `single_user` did not exist, and neither did any auth-disabled or local mode (every
`local_mode` grep hit was `local_model`, a routing concept).

`single_user` was added as a **UI reduction**: one person, so user management, tenant selection
and the whole `/org` surface are hidden. Login stays required. `schema_134` widens the CHECK
constraint to the three values; the downgrade narrows it back only after rewriting
`single_user` rows, otherwise the re-add fails on illegal data.

**The hazard was the shape of the existing guards, not the new value.** Every frontend check was
written as a literal comparison against one of the two known modes:

| Site | Old expression | Naive `single_user` result |
| --- | --- | --- |
| `RequireOrgAdmin.tsx` | `=== "agent_system"` | **`/org` stays reachable** — only `agent_system` bounced |
| `UserMenu.tsx` | `=== "multi_tenant"` | org entry hidden (accidentally right) |
| `AdminInterfacesMemoryPage.tsx` | `=== "agent_system"` | content CMS **disappears** — no other place to manage content |
| `AdminUsers.tsx` ×6 | `=== "agent_system"` | tenant UI hidden (right), but user management itself stayed |
| `OrgContentCms.tsx` / `OrgKnowledgePublishSection.tsx` | `=== "agent_system" ? admin : org` | calls the `/v1/org/...` API, which 404s without an org surface |

A third value read through any of those silently inherits a neighbour's behaviour rather than a
decision. So the frontend got the same treatment the backend got in §7: a predicate module,
`src/auth/deploymentMode.ts`, mirroring `has_org_surface()` / `is_single_user()` from
`operator_settings_readers`, with `deploymentMode()` narrowing the wire value and defaulting to
`multi_tenant` exactly as the backend reader does. Every site now asks the question it means.

What `single_user` hides: the `/org` routes and their nav entry, the tenant column and every
tenant picker in the people admin, the create-tenant form, the **People** group in the admin
sidebar, and `/admin/users` itself (`RequireUserAdmin` bounces it to `/admin`). The content CMS
flips the other way — with no org surface, the platform-admin CMS is the only content store, so
it is shown and pointed at `/v1/admin/tenant-content`.

**Two tenant pickers were not gated at all**, so no amount of fixing the existing comparisons would
have caught them — they simply had no mode check to invert:

- `AdminInterfacesLlmSection.tsx` — the model-access scope `<select>` offered `global | tenant |
  user` plus a tenant dropdown.
- `AdminAgents.tsx` — the agent access-policy scope `<select>`, same three scopes, plus a
  free-text tenant-id input.

Both now drop the `tenant` scope option and its picker when `!hasOrgSurface`. `AdminAgents`
needed more than hiding: its `policyScope` **defaults to `"tenant"`**, so removing the option
alone would leave the `<select>` on a value it no longer offers — rendered blank, and still saved
as `tenant`. The state is coerced to `global` instead. Hiding a control is not the same as
retiring a value; anywhere a hidden option is also a default, the value has to move.

This is the argument for the predicate module over per-site fixes: the inventory of *literal
comparisons* is not the inventory of *tenant surfaces*. The second list has members with no
comparison in them at all.

**A trap worth recording:** `tests/unit/test_frontend_route_manifest_matches_app_routes` parses
`App.tsx` with a line-based heuristic that pairs each `<Route>` with its `</Route>`. A wrapper
`<Route element={<SomeGuard />}>` carries no `path`, so it never pushes a segment — but its
closing tag still pops one, silently stealing `admin` from every sibling route after it. The
guard is therefore composed inline on a single self-closing route
(`<Route path="users" element={<RequireUserAdmin><AdminUsers /></RequireUserAdmin>} />`) rather
than wrapped in an extra level. The heuristic is not wrong so much as brittle; anyone adding a
path-less guard route should compose rather than nest.

## Rejected alternatives

| Option | Why rejected |
| --- | --- |
| Leave `user.manage` / `agent.assign` instance-wide | With three companies on one instance this is a direct isolation break, not a theoretical one. |
| Build (c) now | 17–26 days for a capability nobody has a trigger for, and it is the highest-risk shape change available in this codebase. Deferred behind recorded triggers instead. |
| Add `tenant_id` to every `UPDATE users` WHERE clause | For a site admin `tenant_filter()` is `None`, so the clause would have to be conditional in 11 places, changing a 130-line handler into a dynamic-SQL builder for no safety gain over the guard that is already there. |
| Mark the guarded `admin_patch_user` writes `site-wide` | False. It would teach the next reader that the endpoint is unscoped when it is not. Hence the `guarded` marker. |
| File-level marker for `identity_tenants.py` | One exempt file is where the next unscoped query hides. Per-function markers cost 7 comment lines and keep every new function in that file checked. |
| Let `tenant_membership_upsert` accept cross-tenant rows and police it at the callers | The callers are where the mistake was made. The invariant belongs on the single write path. |

## Consequences

**Positive**

- A delegated company admin can administer their own people and agents and cannot read, edit,
  create, move or grant against another tenant. The instance is safe to hand out.
- `tenant_memberships` and `users.tenant_id` can no longer disagree through either write path.
- The `tenant_scope` gate makes the *next* unscoped query a failing build rather than a finding
  in a review six months from now.
- (c) has a written door with named triggers instead of being either forgotten or permanently closed.

**Negative / residual risk**

- Three admin concepts now exist: `site_role` (ownership), `capabilities` (what), `AdminScope`
  (where). A new admin surface has to pick the right guard. `require_admin_capability` on a
  target-bearing endpoint reopens exactly what this closed. The convention is: **if the request
  names a target, use `require_admin_scope`.**
- ~~`require_admin` (the legacy role gate) is still used on agent prompt draft/publish and
  `admin_get_agent`~~ — closed in the follow-up pass recorded in §7. `require_admin` no longer
  appears at any call site; it survives only as the `require_site_admin` alias definition.
- The `guarded` marker is an escape hatch. It is greppable and requires a reason, but a careless
  one is not caught statically — only in review.
- ~~Moving a user does **not** move chat history, workspaces, media or shares~~ — workspaces now
  follow the owner (`move_user_tenant` updates `project_workspaces.tenant_id` in the same
  transaction). Chat history, media and shares still do **not** move, and the move still writes
  no audit row. A migration is currently "the person changes tenant, and their workspaces come
  along"; it is not "everything the person made moves". Anyone performing one must decide
  explicitly what happens to the rest of the old data.
- There is still no platform-wide audit log. Only `tenant_content` has review history.
- `users_email_key UNIQUE(email)` is global, so one email is still one person. Until (c) exists,
  a person employed by two tenant companies needs two accounts and two email addresses.

## Verification

- `pytest tests/unit/test_p6_capabilities_rbac.py` — 25 tests. Delegated scope confined to own
  tenant; site-admin scope unfiltered; PATCH across tenants 403; move requires site-wide; same-value
  tenant echo allowed so the admin UI can post the row back verbatim.
- `pytest tests/unit/test_p6_agent_assign_scope.py` — 15 tests. Includes the OR-join trap
  (`?user_id=` across tenants) and `scope='global'` being site-wide only.
- `pytest tests/unit/test_tenant_membership_invariant.py` — 10 tests. Ghost membership rejected;
  unknown user rejected; move carries the row, clears other tenants, and never reads the old role.
- `pytest tests/unit/test_tenant_scope_value_object.py` — 9 tests on `TenantScope`.
- `pytest tests/unit/test_tenant_scope_check.py` — 18 tests on the gate: what it flags, what it
  must not flag, both markers, function-level coverage, and no leaking to sibling functions.
- `pytest tests/unit/test_p8_tenant_scope_conversion.py` — 10 tests on the §7 conversions:
  workspace reindex across tenants, per-user model access refused before the write happens, RAG
  ingest using the actor's tenant, and `ingest-docs` calling the site guard rather than the scope
  guard.
- `pytest tests/unit/test_prompt_publish_risk_gate.py` — 19 tests on §9. Domain: fenced and bare
  JSON, unusable level, empty content, non-JSON and provider exception all fail closed; the
  assessment uses a short timeout rather than the 120 s default. Handler: low publishes and
  records the level, high blocks a delegated admin, a site admin needs a non-empty reason
  (whitespace does not count), a valid override records who, an unavailable assessment 503s
  without publishing, and a disabled gate never spends a provider call.
- `pytest tests/unit/test_tenant_membership_invariant.py` — 12 tests, including that a tenant
  move carries owned workspaces along and that a same-tenant move touches none.
- `pytest tests/unit/test_single_user_deployment_mode.py` — 14 tests on §10's backend half: the
  canonical three-mode list, the forms re-export identity, reader normalisation, unknown/unset
  falling back to `multi_tenant`, a parametrized predicate matrix over all three modes, the
  predicates never both being true, and the patch writer using the canonical list instead of its
  own hardcoded pair.
- `npx vitest run src/auth/deploymentMode.test.ts` — 9 tests on the frontend mirror: narrowing,
  case/whitespace tolerance, the `multi_tenant` fallback, and that the two predicates give three
  distinct signatures across the three modes (`agent_system` is deliberately neither).
- `npx vitest run` — 36 passed across 6 files. `npm run i18n:check` — en ↔ de key parity OK for
  the new `setup:modeSingle*` keys. `npx vite build` — succeeds.
- `tsc --noEmit` was compared against a clean `HEAD` worktree: 271 errors before, 271 after,
  identical per file. The repo carries a large pre-existing i18n `TFunction` typing debt and
  `tsc` is not in the build gate; this change adds none of it.
- `pytest tests/unit` — 1434 passed, 2 skipped.
- `CHECK_PROFILE=fast python3 scripts/checks/run.py` — all checks pass with the gate integrated.
- `python3 scripts/preflight_tenancy.py --dsn ...` — read-only preflight for a real instance:
  deployment mode, tenants, site admins, per-tenant volume, tables without an FK to `tenants`,
  orphan rows. Run it against the production instance before relying on any of the above there.
