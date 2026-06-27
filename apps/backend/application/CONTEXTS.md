# Application Contexts

This layer is organized by workflow boundaries. It should absorb orchestration
that currently lives in broad domain modules, while keeping pure decisions in
`apps.backend.domain`.

## Context Map

- `agent_runtime`: chat turns, planning, tool execution loops, agent IO, run
  persistence orchestration.
- `collections`: collection commands and queries, dashboard projection writes,
  attachment coordination.
- `dashboards`: dashboard creation, retrieval, layout/data replacement, and
  dashboard repository workflows.
- `identity`: user and tenant queries plus role-change workflows.
- `model_routing`: model route selection workflows and provider call setup.
- `providers`: operator provider endpoints and model catalog preference
  workflows.
- `rag`: document ingestion, retrieval bootstrap, workspace/document indexing.
- `sharing`: dashboard and collection grant workflows.
- `setup`: instance setup, setup catalog, onboarding/install workflows.
- `studio`: studio jobs and catalog workflows.
- `tools`: plugin/tool registry, routing, policy, invocation orchestration.
- `voice`: STT/TTS/realtime turn workflows.
- `workspace`: workspace creation, resolution, and workspace-bound operations.

## Migration Rule

Move code here when it coordinates more than one dependency, performs side
effects, loads persisted state, calls providers, or prepares runtime IO.

Keep code in `domain` when it is a pure rule, value object, policy, aggregate,
repository protocol, or deterministic classifier.
