---
doc_id: strategic-design
domain: agentlayer_docs
tags: [architecture, ddd, strategic-design]
---

## Purpose

This document captures AgentLayer's strategic Domain-Driven Design. It defines
the product language, bounded contexts, ownership boundaries, and integration
relationships that should guide tactical code changes.

Use this document before large refactors or new runtime features. Tactical DDD
modules are useful only when they support these boundaries and invariants.

## Publication Boundary

This document is safe for normal repository documentation. It should describe
concepts, responsibilities, and boundaries without exposing:

- secrets, tokens, provider credentials, or private endpoints
- exploit procedures or bypass recipes
- tenant-specific operational incidents
- private commercial roadmap details

Operational security details belong in internal runbooks, not public strategic
design.

## North Star

AgentLayer's long-term goal is a generic, governed runtime for autonomous and
semi-autonomous Agents. The same platform should support everyday personal
tasks, dashboards, research, media workflows, coding projects, review/security
workflows, scheduled unattended execution, and a personal delegate that can
represent the user within explicit memory and autonomy bounds.

The strategic direction is:

- start with strong general-purpose models where capability is highest
- measure what each model/Agent combination can actually do
- tune the harness globally first, then add model/provider-specific overrides
- rank models by empirical quality for each Agent profile and task family
- make orchestration, retrieval, planning, execution, and verification explicit
- let a personal delegate learn stable preferences, project context, and
  communication style without bloating every prompt
- progressively support smaller/local/edge models by reducing context bloat,
  improving tool routing, and moving knowledge into structured retrieval
- keep dashboards, tools, sharing, and Agents generic rather than building
  one-off vertical apps

Autonomy is not a single feature. It is the result of reliable planning,
bounded tool execution, retrieval quality, model selection, governance, and
measurable feedback loops.

A personal delegate is not a raw clone of the user. It is a governed Agent that
uses memory, preferences, current project context, and explicit autonomy policy
to decide when it can act, when it should draft, and when it must escalate.

## Ubiquitous Language

- **Agent**: a persona plus runtime policy. An Agent defines behavior,
  prompt(s), tool access, model profile, workspace requirements, and governance.
- **General Agent**: the default orchestrator. It answers directly when possible
  and routes work to specialists through delegation.
- **Specialist Agent**: an Agent intended for a focused domain, such as Coding,
  Research, Dashboard, Media, Math, or Security Auditor.
- **Operator Agent**: an admin specialist for AgentLayer platform operations,
  settings, tool registry, scheduler jobs, and runtime governance.
- **Tool**: an executable capability loaded from the live tool registry.
- **Tool Domain**: a package-level grouping for tools, such as coding,
  dashboard, media, or platform.
- **Tool Capability**: a fine-grained declared capability used to resolve tool
  access without hardcoding exact tool names.
- **Direct Agent Access**: a user may explicitly select or invoke an Agent.
- **Delegate Access**: the orchestrator may route work to a Specialist Agent.
- **Effective Agent**: the fully resolved Agent for a request after applying
  file defaults, tenant overrides, user/access policies, model profile, tool
  policies, and prompt versions.
- **Prompt Version**: a tenant-scoped draft, published, or archived prompt for
  an Agent. Drafts do not affect runtime until published.
- **Provider**: a configured model-serving backend or external LLM endpoint.
- **Model Profile**: a logical runtime profile such as default, agent, coding,
  embedding, extractor, STT, or TTS.
- **Workspace**: a bound code/project environment available only to Agents whose
  runtime policy allows workspace use.
- **Dashboard**: a user-facing stateful surface with layout and JSON data; some
  Agents may operate on dashboards, others may not.
- **Tenant Policy**: policy scoped to one tenant. It may affect model access,
  Agent access, prompt versions, and tool effectiveness.
- **User Policy**: policy scoped to one user. It is more specific than tenant
  policy and should be used sparingly for exceptions.
- **Harness**: the benchmark and evaluation control plane used to test Agents,
  tool routing, prompts, models, providers, and runtime policies.
- **Canonical Prompt**: a stable benchmark prompt designed to measure a known
  capability without user-specific noise.
- **Real Prompt**: a captured or curated real-world prompt used to validate that
  benchmark quality transfers to actual user workflows.
- **Autonomous Run**: an Agent execution that can plan, call tools, verify
  progress, and finish or escalate within explicit governance bounds.
- **Personal Delegate**: a governed Agent that can represent the user for
  bounded decisions using user preferences, memory, project context, and
  explicit autonomy rules.
- **Persona Memory**: stable facts about user preferences, communication style,
  goals, and constraints. It should be retrieved when relevant, not injected
  wholesale into every prompt.
- **Project Memory**: workspace- or project-scoped knowledge, decisions,
  conventions, and goals used only when the active context matches.
- **Context Capsule**: a compact, purpose-built context block assembled from
  memory, workspace, dashboard, task, and recent conversation for one Agent run.

## Bounded Contexts

### Agent Runtime

Owns chat turn preparation, Agent selection, delegation, tool loop behavior,
context budgets, prompt injection, and runtime recovery guards.

Key decisions:

- Which Agent is effective for a request?
- May this user invoke or delegate to this Agent?
- Which tools are forwarded to the model for this round?
- Which prompt and context budget apply?

### Agent Governance

Owns Agent access policies, prompt versions, Agent defaults, Effective Agent
preview, and admin-facing governance workflows.

Key decisions:

- Which direct/delegate access state applies?
- Which prompt version is currently published?
- What is the difference between file default, tenant override, and effective
  runtime state?
- Which changes require draft/publish/audit?

### Tool Registry

Owns tool discovery, tool metadata, tool domains, declared capabilities, and
operator policy applied to tools.

Key decisions:

- Which tool handlers exist?
- What metadata and policy apply to a tool package?
- Which tool names are effective after operator policy?

### Model Routing And Providers

Owns provider catalog, model defaults, provider/model access policy, and model
profile resolution.

Key decisions:

- Which provider and model serve this Agent turn?
- Is the selected provider/model allowed for this user or tenant?
- Which fallback or routing policy applies?

### Workspace

Owns code workspace records, access, indexing, verification policy, and
workspace-bound runtime context.

Key decisions:

- Which user can access a workspace?
- Can an Agent use workspace tools for this request?
- What verification policy applies before finishing?

### Dashboard

Owns dashboard templates, layout/data persistence, sharing, and dashboard-level
Agent restrictions.

Key decisions:

- Which dashboard data is available to an Agent?
- Which tools may operate on dashboard state?
- Which dashboard sharing policy applies?

### Identity And Tenant

Owns users, roles, tenants, auth, and identity context used by all other
contexts.

Key decisions:

- Who is the caller?
- Which tenant is active?
- Which role and user-scoped exceptions apply?

### Knowledge And RAG

Owns document ingestion, retrieval, workspace knowledge, memory graph, and
evidence surfaces.

Key decisions:

- What knowledge can be retrieved for this user, tenant, workspace, or Agent?
- Which retrieval budget applies?
- Which extraction model/profile is used?
- Which persona/project memories are relevant enough to enter the context
  capsule?

### Personal Delegate And Memory

Owns user-level delegate preferences, autonomy bounds, communication style,
goals, project overlays, and auto-response decisioning.

Key decisions:

- May the delegate act, draft, wait, or escalate?
- Which user memories are relevant for this turn?
- Which project/workspace overlay changes the user's default preferences?
- Which actions require explicit confirmation?
- How should the system avoid pretending to know the user when memory evidence
  is weak?

### Scheduling And Tasks

Owns scheduled jobs, backlog tasks, artifacts, and unattended execution targets.

Key decisions:

- Which Agent executes a scheduled job?
- What tools, workspace, and model profile are allowed unattended?
- What artifacts and audit trail are produced?

### Evaluation And Harness

Owns benchmark manifests, scenario definitions, canonical prompts, real prompt
sets, scoring, model/provider comparisons, and runtime tuning recommendations.

Key decisions:

- Which scenarios prove an Agent capability?
- Which model/provider/profile performs best for a task family?
- Which harness overrides are justified by evidence?
- Which regressions block a prompt, tool, or routing change?

## Context Map

```text
Identity/Tenant
  -> Agent Governance
  -> Model Routing And Providers
  -> Tool Registry
  -> Workspace / Dashboard / Knowledge

Agent Runtime
  -> Agent Governance       (effective Agent, access, prompt)
  -> Model Routing          (provider/model)
  -> Tool Registry          (forwarded/effective tools)
  -> Workspace/Dashboard    (request context)
  -> Knowledge/RAG          (retrieval context)
  -> Personal Delegate      (preferences, autonomy, persona context)
  -> Scheduling/Tasks       (unattended or artifact flows)
  -> Evaluation/Harness     (quality feedback and tuning)
```

The Agent Runtime is the orchestration hub, but it should not own every policy.
Policies belong to the context that owns the language and invariants.

## Strategic Invariants

- An Agent is not a tool. It is a governed runtime persona.
- Direct access and delegate access are different decisions.
- File defaults are product defaults; admin changes are tenant/user overrides.
- Draft prompt versions must not affect runtime until published.
- Effective state must be previewable before it is used.
- Tool access is resolved from registry metadata and operator policy, not from
  prompt text.
- Model/provider access is independent from Agent access, but both must be
  satisfied for a turn to run.
- Workspace and dashboard capabilities are explicit runtime permissions.
- Autonomy must be measurable before it is trusted.
- Harness results should drive model/profile/prompt/tool-routing changes.
- Real prompt evaluation should complement canonical benchmark scenarios.
- Persona memory must be scoped, retrieved, and cited by relevance; it must not
  become an always-on prompt dump.
- Personal delegate autonomy must be bounded by explicit user, tenant, and
  project policy.
- When the system is representing the user, it should distinguish between
  acting, drafting, recommending, and escalating.
- Edge/local model support requires stricter context budgets and better
  retrieval, not larger prompts.
- Dashboards and sharing should remain generic primitives, not hardcoded
  product silos.
- Security-sensitive details belong to internal runbooks, not public
  architecture docs.

## Runtime Resolution Flow

```text
request identity
  -> resolve tenant/user/role
  -> resolve requested/default Agent
  -> evaluate Agent access policy
  -> merge Agent file default + published prompt + config overrides
  -> resolve model profile/provider/model access
  -> resolve tool policy and forwarding budget
  -> prepare workspace/dashboard/knowledge context
  -> assemble relevant persona/project context capsule
  -> run LLM/tool loop
  -> verify result or escalate
  -> persist run trace, artifacts, and audit events
  -> feed benchmark/quality observations back into governance
```

## Autonomy Roadmap

Agent autonomy should be developed in stages:

1. **Assisted execution**: Agents answer or call a bounded set of tools in a
   supervised chat turn.
2. **Planned execution**: Agents create a plan, execute steps, verify progress,
   and summarize results.
3. **Delegated specialist execution**: the General Agent routes work to
   Specialists with clear task prompts and inherited context.
4. **Scheduled unattended execution**: Agents run from scheduler/task triggers
   with strict tool, model, workspace, and notification policy.
5. **Adaptive orchestration**: runtime chooses retrieval, tools, specialist,
   and model profile from measured capability and policy.
6. **Edge/local execution**: smaller models handle bounded workflows through
   compact prompts, structured retrieval, strict tool catalogs, and fallback to
   stronger models when policy allows.

Each stage needs explicit quality gates. Do not rely on anecdotal demos to
promote autonomy levels.

## Personal Delegate Roadmap

The personal delegate should grow in layers:

1. **Preference memory**: capture stable communication and engineering
   preferences with explicit user review.
2. **Project overlays**: apply workspace/project-specific goals, constraints,
   and conventions only when that project is active.
3. **Auto-response decisioning**: decide whether to act, draft, wait, or
   escalate using recent conversation plus delegate config.
4. **Draft-first representation**: write suggested responses or task plans in
   the user's style without sending/executing risky actions automatically.
5. **Bounded autonomous action**: execute low-risk tasks where autonomy policy
   allows it and verification is available.
6. **Cross-surface representation**: operate across chat, dashboards, tasks,
   workspaces, and communication channels with the same policy and memory
   model.

The goal is not to store "everything about the user" in the prompt. The goal is
to retrieve the smallest useful context capsule for the current task, with clear
scope and confidence.

## Quality And Harness Strategy

Quality should be measured at several layers:

- **Canonical benchmarks** for stable capability checks.
- **Real prompt suites** for messy user workflows and regression confidence.
- **Model/provider ranking** per Agent profile and task family.
- **Tool-routing metrics** for correct tool selection and schema use.
- **Retrieval metrics** for answer grounding, recall, and context efficiency.
- **Verification outcomes** for coding, security, and scheduled execution.

The harness should support:

- global defaults for runtime behavior
- model/provider-specific overrides when evidence supports them
- prompt and tool-policy experiments
- before/after comparison for governance changes
- clear promotion criteria for stronger autonomy

The target is not "one best model." The target is an evidence-backed matrix:

```text
Agent profile x task family x provider/model x tool policy -> measured quality
```

## Dashboard And Sharing Strategy

Dashboards should remain generic presentation and interaction surfaces. They
should support many element types so Agents can visualize and operate on varied
data without creating a bespoke UI for every workflow.

Strategic dashboard goals:

- generic blocks and layouts for many data shapes
- Agent-created and user-edited dashboard state
- granular sharing for dashboards, collections, workspaces, and artifacts
- clear separation between dashboard state and tool permissions
- reusable templates for common workflows without locking the domain model to a
  single vertical

Sharing should be policy-driven and granular. Everyday tasks, personal
knowledge, media workflows, coding projects, benchmark artifacts, and security
reports should all use the same sharing concepts where possible.

## Documentation Rules

- Strategic docs explain language, context boundaries, and invariants.
- Tactical docs explain modules, APIs, stores, and migration steps.
- Runbooks explain operational procedures and sensitive details.
- ADRs record irreversible or high-impact architecture decisions.

When adding a new Agent feature, update the strategic docs if it changes
language or boundaries. Update tactical docs if it only changes implementation.
