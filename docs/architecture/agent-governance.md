---
doc_id: agent-governance
domain: agentlayer_docs
tags: [architecture, ddd, agents, governance]
---

## Purpose

Agent Governance defines how AgentLayer manages Agents as product/runtime
objects: who may use them, which prompts are effective, which tools and models
apply, and how admins can preview and change behavior safely.

This document is strategic and product-facing. Operational secrets, exploit
details, or deployment-specific provider endpoints do not belong here.

## Core Model

An **Agent** is the combination of:

- identity: `id`, `name`, icon, description
- persona: system prompt and behavior rules
- access policy: direct invocation and delegation
- tool policy: allowlist, domains, capabilities, pinned tools
- model policy: model profile and provider/model access
- context policy: workspace, dashboard, retrieval, history, and tool budgets
- governance state: file default, tenant override, user exception, prompt
  versions, and audit trail

The runtime should never infer these from prompt text. Prompts guide behavior;
policies decide permission.

## Defaults And Overrides

AgentLayer uses layered configuration:

1. **File defaults** in `plugins/agents/<id>/agent.yaml` and
   `system_prompt.md`.
2. **Tenant governance** in database policies and prompt versions.
3. **User exceptions** for access policy only when needed.
4. **Runtime effective state** resolved per request.

File defaults are versioned with code. Database state is operational
configuration and must be auditable.

## Access Policy

Access has two independent decisions:

- **Direct access**: the user may explicitly invoke/select the Agent.
- **Delegate access**: the General Agent may route work to the Agent.

This distinction matters because a user may not need direct access to a
specialist, while the orchestrator may still delegate bounded work to it.

### Access States

Each scoped policy can set:

- `inherit`: use the default or less-specific policy
- `allow`: explicitly allow this access mode
- `deny`: explicitly deny this access mode

The effective decision is resolved from defaults plus global, tenant, and user
policy. Role hard-gates such as admin-only direct invocation remain hard
security boundaries unless a future design explicitly changes that invariant.

## Prompt Versioning

Prompt editing uses Draft/Publish semantics:

- **Draft**: saved version that does not affect runtime.
- **Published**: active tenant prompt used by runtime.
- **Archived**: previous published version or retired draft.

Publishing a prompt archives the previous published prompt for the same
tenant/Agent and makes the new prompt effective for future requests.

### Prompt Guardrails

Prompt editing should always show:

- character and approximate token budget
- effective source: file default, DB published, or future override
- version number and publish status
- diff or preview before publishing
- author and timestamp metadata

Prompt text must not become the place for access control. Use policy fields for
permissions and prompts for behavior guidance.

## Effective Agent

The **Effective Agent** is what runtime actually uses. It is resolved from:

```text
agent file default
  + tenant/user access policy
  + published tenant prompt version
  + config overrides
  + tool operator policy
  + model/provider policy
  + workspace/dashboard/request context
```

Admin UI must expose Effective Preview so admins can understand what will
happen before publishing or changing policy.

## Tool Governance

Agent tool access is based on:

- explicit `tool_allowlist`
- `tool_domains`
- `tool_capability_any`
- `pinned_tools`
- operator tool policy
- request/round forwarding budget

Tools should be grouped by domain/capability in UI. Full tool schema forwarding
is a runtime optimization choice, not an Agent identity decision.

## Model Governance

Agents use model profiles rather than hardcoding provider/model IDs in prompts.

Examples:

- General Agent: default or agent profile
- Coding Agent: coding profile
- Security Auditor: accurate/admin-reviewed coding profile
- Math Agent: small/local model may be enough

Provider/model access policy must still approve the resolved model for the
tenant/user.

## Workspace And Dashboard Governance

Agents should declare whether they require or may use workspace/dashboard
context.

Examples:

- Coding and Security Auditor require workspace context.
- Dashboard Agent may operate on dashboard state.
- Math and Lifestyle should not receive workspace tools unless explicitly
  designed to.

Workspace and dashboard access are not implied by being an admin Agent.

## DDD Placement

Recommended ownership:

- `domain/agent_runtime`: pure policy decisions, effective access, value objects
- `application/agent_runtime/use_cases`: resolve effective governance, create
  prompt drafts, publish versions, update policies
- `infrastructure/agent_runtime`: YAML loading, DB stores, config overlays
- `api/agents/controllers`: HTTP DTOs and auth only
- `frontend/admin/agents`: preview, editor, publish UI, policy controls

API controllers should not decide policy. They should authenticate, validate
transport input, and call application use cases.

## Admin UI Shape

Admin -> Agents should present:

- registry/file defaults
- effective access preview
- direct/delegate policy controls
- prompt editor with draft/publish/version history
- resolved tools and effective tools
- model profile and effective model/provider
- context budget and prompt budget
- audit trail and rollback affordances

Agent import should remain analyze-first. Writing imported Agents or tools
should require explicit review and publish steps.

## Autonomy Governance

Autonomous Agents must be promoted through explicit capability levels rather
than enabled as a single boolean.

Recommended levels:

1. **Chat-only**: answer from prompt/context with no action tools.
2. **Tool-assisted**: call allowed tools in a supervised chat turn.
3. **Plan-and-execute**: produce a plan, execute bounded steps, verify, then
   summarize.
4. **Delegated specialist**: receive scoped tasks from the General Agent and
   return artifacts/results.
5. **Scheduled unattended**: run from scheduler/task triggers with notification
   and escalation rules.
6. **Adaptive autonomous**: choose retrieval, tools, specialist, and model
   profile from measured capability within policy.

Each level requires:

- allowed tools and denied tools
- model profile and fallback policy
- context/retrieval budget
- verification or escalation criteria
- benchmark evidence
- audit trail

Small/local/edge models should start at lower autonomy levels and earn more
responsibility through measured benchmark and real-prompt performance.

## Harness And Model Ranking

Agent Governance should integrate with the benchmark harness. The harness is
the evidence source for prompt, tool-routing, model, and autonomy changes.

The evaluation strategy should include:

- canonical prompts for stable capability checks
- real prompts for transfer to actual user workflows
- model/provider rankings per Agent and task family
- global harness defaults
- model/provider-specific harness overrides when evidence supports them
- before/after comparisons for prompt versions and policy changes

Governance decisions should prefer measured results over intuition. A published
prompt, model override, or autonomy-level increase should be explainable by
benchmark or review evidence.

Example matrix:

```text
Agent: coding
Task family: repo edit + verify
Model profile: coding
Provider/model: provider_1/model_x
Prompt version: v12
Tool policy: coding_build
Result: pass rate, tool errors, verification success, latency, cost
```

## Edge And Local Model Strategy

The long-term platform should support strong hosted models and smaller local or
edge models. Governance must make that safe by reducing ambiguity:

- compact prompts with versioned changes
- small tool catalogs through routing and pinned tools
- structured retrieval instead of dumping large history
- explicit context budgets per model
- fallback to stronger models when policy allows
- autonomy levels tied to measured model capability

Edge readiness is not only a model problem. It depends on orchestration,
retrieval quality, tool schema discipline, context trimming, and verification.

## Personal Delegate And Auto-Response

AgentLayer should support a personal delegate: an Agent that can represent the
user within explicit memory, project, and autonomy bounds. This is different
from a general-purpose assistant. The delegate acts from the user's configured
preferences and relevant memory, but it must not pretend to be omniscient or
invent personal intent.

The personal delegate should decide among four outcomes:

- **wait**: no useful action is available yet
- **draft**: prepare a response, plan, or action proposal for review
- **act**: execute a low-risk allowed action
- **escalate**: ask the user or admin because policy, risk, or missing context
  prevents autonomous action

Auto-response should use this decisioning flow rather than simply generating a
message whenever a conversation is idle.

## Memory Governance

Personal memory must be scoped and retrieved. It should not be appended as one
large always-on prompt.

Recommended memory scopes:

- **user persona**: stable preferences, tone, long-term goals, constraints
- **workspace/project**: repository conventions, current goals, decisions,
  coding style, verification expectations
- **tenant/team**: shared norms and policies
- **conversation/task**: recent local context and active objective
- **dashboard/artifact**: state attached to a specific surface or output

Memory should enter a run through a compact context capsule:

```text
task intent
  + relevant persona preferences
  + project/workspace overlay
  + active dashboard/task/artifact state
  + recent conversation summary
  + confidence / source metadata
```

The capsule should be budgeted. If memory is weak, stale, or irrelevant, the
Agent should omit it or lower confidence instead of bloating context.

## Representation Boundaries

When an Agent represents the user, governance must distinguish:

- speaking in the user's preferred style
- making a recommendation on the user's behalf
- drafting a message for the user
- sending or committing an action as the user

Only the last category requires the highest trust level. Most workflows should
start as draft-first until benchmarks and user feedback show that autonomous
action is reliable.

Representation should be project-aware. The user's preferences for a personal
project, a production codebase, a shared dashboard, and a casual message may be
different. Workspace and task overlays should override generic persona memory
only for the relevant context.

## Public Vs Internal Details

Safe for normal architecture docs:

- concepts and boundaries
- policy layers
- effective resolution flow
- DDD ownership
- admin UX principles

Keep internal:

- private provider endpoints
- token and secret handling procedures
- abuse paths for risky tools
- incident-specific weaknesses
- production tenant details

## Open Questions

- Should user-scoped prompt overrides exist, or should prompts remain
  tenant-scoped for auditability?
- Should prompt publish require approval for production tenants?
- Should Agent model profile overrides live with Agent Governance or with Model
  Routing policy?
- Should workspace/dashboard permission become first-class Agent policy fields
  instead of inferred from tool availability?
- Should Agent Governance emit domain events for prompt publish and policy
  changes?
- Should personal delegate memory require explicit user approval before it can
  influence auto-response?
- How should memory confidence and source attribution be shown in Admin/User UI?
- Which communication surfaces are allowed to send automatically, and which
  must remain draft-only?
