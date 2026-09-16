---
doc_id: adr-0011-roles-and-agent-access-without-tenancy
domain: agentlayer_docs
tags: [adr, rbac, roles, tenant, identity, agent-access, site-admin, capabilities]
---

# ADR 0011: Roles and agent access without tenancy

## Status

**Accepted.** Implemented across P1–P7 (`5284f0e` … `84be7e3`): elevation moved onto
`users.site_role`, delegated admin capabilities landed in `schema_130`, the agent submission
queue in `schema_131`. `pytest tests/unit` is green (1303 passed, 2 skipped).

Two things this ADR decides that are worth re-reading before touching the identity layer:
§2 (why `users.role` must never again grant privilege) and §5 (why the KI pre-check is
advisory and the human gate is not).

Analysis this is derived from: [`docs/planning/roles-and-agent-assignment-analysis.md`](../planning/roles-and-agent-assignment-analysis.md).
Feature doc with the concrete anchors: [`docs/features/agent-registry-and-allowlists.md`](../features/agent-registry-and-allowlists.md).

## Context

The instance is self-hosted for roughly ten people split into informal friend groups with
different rights: one person should be able to code (coding agent + workspace), others should
only chat or use the knowledge companion, and some should never see dashboards or workspaces at
all. The owner wants to administer this **per person**, keep the admin burden near zero, and
still have a notion of "roles with permissions" rather than a pile of ad-hoc flags.

That collides with the tenancy model the codebase was built around. `operator_settings.deployment_mode`
can be set to `agent_system`, which turns the whole `/v1/org/*` surface off — `require_tenant_admin`
and `require_tenant_member` return 404, and the profession policy in `/auth/me` stops applying.
Everyone lives in tenant 1. So the natural home for "who may do what" is no longer a tenant, and
the tenant machinery cannot carry the decision.

Worse, the existing role fields were overloaded. `db.user_site_role()` mapped a legacy
`users.role = 'admin'` onto `site_admin`, and `is_elevated_role()` then granted **every** agent
and full `/v1/admin/*` access on the strength of that one string. There was no way to say
"this person is an admin-ish user" without also saying "this person owns the instance". Handing
a friend `role='admin'` to let them assign agents would have handed them the whole box.

Separately, agent release had no review path at all. Agent definitions are files on disk
(`plugins/agents/<id>/agent.yaml` + `system_prompt.md`); `POST /v1/admin/agents/import/analyze`
was a heuristic preview that persisted nothing. The owner explicitly wants users to be able to
*propose* agents with an automated pre-check and a manual admin review, and explicitly wants the
human gate to stay.

## Decision

### 1. `users.site_role` is the only source of elevation

`site_role ∈ {site_admin, site_user}` decides instance-level power. The legacy `users.role`
column no longer grants agent privileges or admin-route access: every elevation check resolves
through `db.user_site_admin(user_id)` instead of reading `users.role`. That covers the chat turn
(`chat_run_bootstrap.py`), the bridge path (`bridge_agent_session.py`), the agent catalog
(`agent_catalog.py`) and the auto-workspace path (`auto_workspace.py`).

A user with `role='admin'` and `site_role='site_user'` therefore sees no admin agents, cannot
reach `/v1/admin/*`, and is subject to the end-user default set like anyone else.

**Why this direction and not deleting `users.role`:** the column is still written on user creation
and read by legacy surfaces. Repointing the *checks* is a small, reviewable change that closes
the privilege-escalation path; removing the column is a migration with a much wider blast radius
and no additional safety. The column is now inert with respect to authorization.

### 2. Delegated administration is capabilities, not booleans (Weg B)

Admin scope lives in JSONB capability sets rather than a fixed column per surface:

- `users.capabilities` — directly granted capabilities.
- `tenant_profession_roles.capabilities` — role-carried capabilities, cumulative across a user's roles.
- `domain/access/capabilities.py` — pure evaluation: a site admin holds every capability
  implicitly; everyone else must carry the slug explicitly. An unknown or missing slug **fails
  closed**.
- `require_admin_capability(request, capability)` in `infrastructure/identity/auth.py` is the
  guard. Admin user endpoints gate on `user.manage`, admin agent endpoints on `agent.assign`.

The shipped capability set is `agent.assign`, `user.manage`, `workspace.manage`,
`dashboard.manage`. `schema_130` also dissolved the `role_kind` CHECK constraint and gave
`user_profession_assignments` a surrogate PK with a uniqueness constraint, so one user can hold
several roles that add up — the old PK `(user_id, tenant_id)` made "coder *and* dashboard
editor" unrepresentable.

**Hard boundary, enforced in the handlers:** a delegated holder can never read, modify or create
a `site_admin`. `admin_users_api` refuses the operation when the target's `site_role` is
`site_admin` and the actor is not a site admin. Delegated power cannot widen itself.

**Why Weg B over Weg A (scope booleans on `users`).** Weg A was the smaller change and was
recommended for ten users. Weg B was chosen anyway because the boolean shape would have needed a
new column for every future admin surface, and because the role-carried capability set lets a
persona ("Editor" = dashboard + workspace manage) be defined once and assigned to several
people. The extra cost was one migration and one pure evaluation module, not a framework.

### 3. Agent entitlement stays in `agent_access_policies`

No parallel system was introduced for "may this user use this agent". The existing
`agent_access_policies` table (scope `global` / `tenant` / `user`, `direct_state` and
`delegate_state` ∈ `inherit` / `allow` / `deny`) is the single place, and the People-admin UI
writes `scope='user'` rows against it. Rows resolve `global → tenant → user` with the last
non-`inherit` winning.

With tenancy off, the `tenant` scope simply goes unused and the `user` scope does the work. That
is deliberate: the day tenancy is ever switched back on, the same rows and the same resolution
order still apply, and nothing has to be re-learned or migrated.

`GET /v1/agents` is filtered through the same `user_may_invoke_agent()` check that the send path
uses, and no longer leaks `system_prompt` or tool configuration to unprivileged callers. Seeing
an agent and being able to run it are the same answer.

### 4. Tenancy stays off; the UI follows the mode

`deployment_mode = agent_system` hides tenant selection, the tenant column and "create tenant"
from the People admin. Friend groups stay virtual — they are not modelled as tenants, and no
feature should start assuming they are.

### 5. Agent release: DB staging, advisory KI pre-check, mandatory human gate

`schema_131` adds `agent_submissions` with a `pending → approved | rejected` lifecycle. Any
authenticated user may submit a draft; nothing about a draft is live until a site admin approves
it, at which point it is materialised into `plugins/agents/<slug>/` and the registry reloads
without a restart. Rejections stay in the queue with their review notes, so the decision record
survives.

`POST /v1/agents/submissions/assess` is the pre-check: it shares the store's validation, slug
and risk logic so the assessment and the eventual row agree, and reports risk level, unknown
tools and a missing description without writing anything.

**The pre-check is advisory and keyword-based.** It does not gate, and the current implementation
is not an LLM pass. This is a decision, not an unfinished state: an automated check that could
approve would make the release decision depend on something whose judgement we cannot audit. The
human review is the control; the pre-check only reduces what the reviewer has to read.

## Rejected alternatives

| Option | Why rejected |
| --- | --- |
| Keep `users.role` as an elevation source | One string granting instance ownership is the exact escalation this ADR exists to close. |
| Weg A — scope booleans on `users` | One new column per admin surface, no reusable personas. Cheaper now, more expensive per feature forever. |
| Re-enable multi-tenancy for friend groups | Modelling ~10 friends as tenants is ceremony without benefit, and it makes every future permission question a two-axis question. |
| Default-deny agents with a default policy | `model_access_policies` + `model_default_policies` show the shape, but flipping agents to default-deny breaks every existing non-admin user at once. Not worth the blast radius while the per-user grant path works. |
| KI review as the gate | Unauditable release decisions. Also redundant: a reviewer is already in the loop. |
| Git-flow submissions (branch + PR) | Genuinely reviewable and attributable, but requires every submitter to have repo access. DB staging was the only option that works for non-contributors. |

## Consequences

**Positive**

- A friend can be given `agent.assign` and hand out coding access without being able to touch
  site-admin anything. The original "one person should be able to code" ask is a single dialog.
- The privilege-escalation path through `users.role` is closed, so the standing warning that
  nobody may be given `role='admin'` no longer applies.
- Multi-role users are representable; capabilities are cumulative and fail closed.
- Agent proposals are possible without filesystem access, and every decision is recorded.

**Negative / residual risk**

- Two admin axes now exist — `site_role` for ownership, `capabilities` for scope. New admin
  surfaces must pick one explicitly; the wrong choice silently grants too much. The convention is
  `require_admin_capability`, not `require_admin`.
- `require_permission(action, resource_type)` still validates nothing — it only resolves identity
  and lets site admins through. It must not be treated as an enforcement point.
- **Scheduled jobs bypass the agent access layers.** `domain/scheduling/targets.py` checks only
  `schedulable` and `min_role`, so a user with the schedules entitlement can reach an agent
  through a job that chat denies them. Open hardening item, not accepted design.
- The submission queue materialises into the plugin directory. A reviewer approving a draft is
  writing files the running instance loads; the review is the only thing standing between a
  proposed prompt and production.
- The pre-check is keyword-based and will miss real risk. Reviewers must read the prompt, not the
  badge.

## Verification

- `pytest tests/unit/test_agent_access.py` — the `role='admin'` + `site_role='site_user'` case
  sees and cannot invoke admin agents; `site_admin` behaves unchanged.
- `pytest tests/unit/test_p6_capabilities_rbac.py` — delegated `agent.assign` can assign; a
  delegated holder attempting to PATCH a `site_admin` fails.
- `pytest tests/unit/test_agent_submission.py` — a draft is inert until approved; rejection
  stays auditable; `assess_submission` writes nothing.
- `pytest tests/unit` — 1303 passed, 2 skipped.
- Ad hoc: a second non-admin account is the fastest check. Walk picker, chat send and
  `/v1/admin/*` together rather than trusting any one of them.
