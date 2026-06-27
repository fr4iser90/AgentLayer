---
doc_id: ddd-architecture-map
domain: agentlayer_docs
tags: [architecture, ddd, backend]
---

## Purpose

This document defines the target Domain-Driven Design workflow and backend
architecture map for AgentLayer.

For the executable checklist and repository checks, see
`docs/architecture/ddd-checklist.md`.

For strategic design language and bounded-context ownership, see
`docs/architecture/strategic-design.md`. For Agent-specific policy, prompt, and
runtime governance, see `docs/architecture/agent-governance.md`.

The current refactor removed direct `apps.backend.domain` imports of
`api`, `dashboard`, `infrastructure`, `integrations`, and `media`. That is the
layering baseline. The next step is not moving files for its own sake; it is
to model the important business areas explicitly and move orchestration into
application use cases.

## DDD Workflow

Use this order before large refactors:

1. **Strategic design**: identify bounded contexts, language, ownership, and
   context boundaries.
2. **Use-case mapping**: list workflows that cross boundaries, such as chat
   completion, tool execution, RAG ingest, dashboard projection, or voice turn.
3. **Tactical design**: define entities, aggregates, value objects, policies,
   domain services, repositories, and domain events only where they clarify
   invariants.
4. **Port design**: define persistence and provider interfaces needed by use
   cases. Repositories model aggregate persistence. External clients are
   application ports.
5. **Adapter implementation**: wire ports to Postgres, provider APIs, file
   storage, MCP, operator settings, and other infrastructure.
6. **Incremental migration**: move one bounded context at a time and preserve
   tests at each step.

## Dependency Rule

Allowed dependency direction:

```text
api
  -> application
    -> domain
    -> infrastructure adapters

infrastructure
  -> application/domain ports
  -> external systems

domain
  -> domain only
```

The domain layer must not import FastAPI routes, DB clients, provider clients,
dashboards, media storage, or integrations. The DDD check enforces this
baseline.

## Backend Layers

### API

`apps/backend/api/` receives HTTP/WebSocket input, validates transport schemas,
resolves identity, and calls application use cases.

API code should not contain business workflows. It should translate:

```text
HTTP/WebSocket request -> application command/query -> HTTP/WebSocket response
```

### Application

`apps/backend/application/` orchestrates use cases. It may coordinate domain
objects, repositories, provider ports, transactions, identity context, and
side effects.

Good application responsibilities:

- run an agent chat turn
- ingest documents into RAG
- append collection items
- resolve a model route and call a provider
- perform one voice realtime turn
- create or update a dashboard from domain state

Application code may depend on domain contracts and infrastructure adapters.

### Domain

`apps/backend/domain/` contains model rules and decisions that can be tested
without Postgres, FastAPI, provider credentials, or filesystem state.

Good domain responsibilities:

- validate aggregate invariants
- calculate effective policies
- classify/rank domain concepts
- parse and normalize value objects
- decide whether a user may do something
- define repository protocols for aggregates

Avoid creating `entities.py` everywhere. A simple policy module is better than
an anemic entity when there is no lifecycle or invariant to protect.

### Infrastructure

`apps/backend/infrastructure/` implements adapters for persistence, provider
clients, settings, runtime services, and external systems.

Infrastructure can be internally modular, but it should not become a god
package. Prefer subpackages by technical concern once a file grows or several
adapters belong together.

## Target Folder Shape

This is the target shape. It should be reached incrementally, not in one large
move.

```text
apps/backend/
  api/
    routes/
    schemas/

  application/
    agent_runtime/
      commands/
      queries/
      dtos/
      use_cases/
      ports.py
    collections/
      commands/
      queries/
      dtos/
      use_cases/
      ports.py
    rag/
      commands/
      queries/
      dtos/
      use_cases/
      ports.py
    voice/
      commands/
      queries/
      dtos/
      use_cases/
      ports.py
    tools/
      commands/
      queries/
      dtos/
      use_cases/
      ports.py

  domain/
    shared/
      ids.py
      errors.py
      events.py

    agents/
      entities.py
      value_objects.py
      policies.py
      repositories.py

    collections/
      entities.py
      value_objects.py
      policies.py
      repositories.py

    tools/
      entities.py
      value_objects.py
      policies.py
      repositories.py

    model_catalog/
      entities.py
      value_objects.py
      policies.py
      repositories.py

    workspaces/
      entities.py
      value_objects.py
      policies.py
      repositories.py

    voice/
      entities.py
      value_objects.py
      policies.py

  infrastructure/
    persistence/
      postgres/
        agent_task_repository.py
        collection_repository.py
        user_repository.py
    embedding/
      client.py
      chunking.py
      providers/
    llm/
      catalog_client.py
      providers/
    settings/
      operator_settings.py
    storage/
      files.py
    tools/
      plugin_registry.py
      mcp_runtime.py
    voice/
      providers/
```

`apps.backend` remains the Python package root for now. Renaming it to
`backend` would be mostly packaging churn and should be a separate decision,
not part of the DDD migration.

## Bounded Context Map

### Agent Runtime

Current areas:

- `apps/backend/domain/agent.py`
- `apps/backend/domain/agent_planner.py`
- `apps/backend/domain/agent_io.py`
- `apps/backend/domain/agent_tools.py`
- `apps/backend/domain/embedded_subagent.py`
- `apps/backend/application/agent_runtime/`

Likely model:

- Entity: `AgentRun`, `AgentTask`, `Artifact`
- Value objects: `AgentId`, `RunId`, `TaskId`, `ToolCallId`, `ModelProfile`
- Policies: task access, delegate enforcement, tool forwarding, approval
- Repositories: `AgentTaskRepository`, `AgentRunRepository`,
  `ArtifactRepository`
- Application use cases: `RunChatCompletion`, `RunEmbeddedSubagent`,
  `ResolveActiveTask`, `RecordToolResult`

### Plugin And Tool Runtime

Current areas:

- `apps/backend/domain/plugin_system/`
- `apps/backend/domain/tool_executor.py`
- `plugins/tools/`

Likely model:

- Entity: `ToolPackage`, `ToolDefinition`, `ToolPolicy`
- Value objects: `Capability`, `ToolName`, `ExecutionContext`, `RiskLevel`
- Policies: capability gates, role/tenant policy, routing policy
- Repositories: `ToolPolicyRepository`
- Application use cases: `ListTools`, `RunTool`, `ReloadToolRegistry`

The registry scans plugin content, but policy resolution and execution logging
are infrastructure concerns.

### Model Catalog And Routing

Current areas:

- `apps/backend/domain/setup/catalog.py`
- `apps/backend/domain/model_routing/resolution.py`
- `apps/backend/domain/model_routing/smart_route.py`
- `apps/backend/infrastructure/model_catalog_providers.py`
- `apps/backend/infrastructure/operator_settings.py`

Likely model:

- Entity: `ModelProvider`, `ModelEndpoint`, `ModelProfile`
- Value objects: `ProviderId`, `ModelId`, `ModelKind`, `ContextWindow`
- Policies: model access policy, smart routing policy, default model policy
- Repositories: `ModelCatalogRepository`, `ModelAccessPolicyRepository`
- Application ports: `ChatCompletionClient`, `EmbeddingClient`

Provider HTTP calls are application ports/infrastructure adapters, not domain
repositories.

### Collections, Dashboards, And Shares

Current areas:

- `apps/backend/domain/collections/`
- `apps/backend/domain/shares/`
- `apps/backend/infrastructure/dashboard_*`
- `plugins/dashboard/`

Likely model:

- Aggregate: `Collection`
- Entity: `CollectionItem`, `Attachment`, `ShareGrant`
- Value objects: `CollectionSlug`, `DataPath`, `FileRef`, `Permission`
- Policies: collection access, share activation, dashboard block visibility
- Repositories: `CollectionRepository`, `AttachmentRepository`,
  `ShareGrantRepository`
- Application use cases: `AppendCollectionItems`, `PatchCollectionFields`,
  `ProjectDashboardData`, `ResolveSharedDashboard`

This is a good first tactical DDD migration because aggregate boundaries are
clear.

### Workspace And Retrieval

Current areas:

- `apps/backend/domain/workspace/`
- `apps/backend/domain/workspace/resolver.py`
- `apps/backend/domain/rag/ingest_common.py`
- `apps/backend/infrastructure/workspace_*`
- `apps/backend/infrastructure/embedding_*`

Likely model:

- Aggregate: `Workspace`
- Entity: `RetrievalIndex`, `IngestJob`, `DocumentChunk`
- Value objects: `WorkspaceId`, `RepoUrl`, `IndexStatus`, `ChunkId`
- Policies: workspace access, index-on-write, retrieval source policy
- Repositories: `WorkspaceRepository`, `IngestJobRepository`
- Application ports: `EmbeddingClient`, `DocumentStore`, `FileTreeReader`

Chunking and provider calls belong in infrastructure/application ports.

### Voice And Media

Current areas:

- `apps/backend/domain/voice/`
- `apps/backend/infrastructure/media/`
- `apps/backend/infrastructure/voice_*`

Likely model:

- Entity: `VoiceProvider`, `VoiceSettings`, `MediaItem`
- Value objects: `VoiceId`, `MimeType`, `QuotaBytes`, `ProviderRole`
- Policies: voice feature policy, upload quota policy, MIME policy
- Repositories: `VoiceSettingsRepository`, `MediaLibraryRepository`
- Application use cases: `RunVoiceRealtimeTurn`, `IngestChatAudio`,
  `SynthesizeSpeech`

STT/TTS provider calls and media file writes are infrastructure.

### Identity And User Context

Current areas:

- `apps/backend/domain/identity.py`
- `apps/backend/domain/http_identity.py`
- `apps/backend/domain/user_persona.py`
- `apps/backend/infrastructure/auth.py`

Likely model:

- Entity: `User`, `Tenant`, `Persona`
- Value objects: `UserId`, `TenantId`, `Role`, `BearerToken`
- Policies: identity trust boundary, persona injection policy
- Repositories: `UserRepository`, `PersonaRepository`

Token parsing and password hashing stay in infrastructure.

## Tactical Building Blocks

### Entity

Use an entity when identity matters over time.

Examples: `AgentTask`, `Collection`, `CollectionItem`, `Workspace`,
`ToolPolicy`, `MediaItem`.

### Aggregate

Use an aggregate when a root protects invariants for child entities.

Examples:

- `Collection` owns metadata and item mutations.
- `Workspace` owns indexing flags and access state.
- `AgentTask` owns status transitions and artifact references.

Only mutate an aggregate through its root.

### Value Object

Use a value object when validation and equality matter but identity does not.

Examples: `CollectionSlug`, `DataPath`, `ModelId`, `ProviderId`,
`Capability`, `Permission`, `MimeType`.

### Domain Service

Use a domain service for pure decisions that do not naturally belong to one
entity.

Examples: model route selection, delegate enforcement, tool routing,
share-access decision.

### Repository

Use a repository for aggregate persistence.

Good:

```python
class CollectionRepository(Protocol):
    def get_by_slug(self, owner_user_id: UserId, slug: CollectionSlug) -> Collection | None: ...
    def save(self, collection: Collection) -> None: ...
```

Avoid repository interfaces for every external API. LLM, embedding, MCP, and
storage calls are better modeled as application ports.

### Application Port

Use an application port for external capabilities needed by a use case.

Examples:

- `ChatCompletionClient`
- `EmbeddingClient`
- `FileStorage`
- `McpRuntime`
- `OperatorSettingsReader`

## Placement Checklist

Use this checklist for new code:

- Does it parse HTTP, WebSocket, request headers, or response schemas?
  Put it in `api`.
- Does it coordinate multiple operations or side effects?
  Put it in `application`.
- Does it enforce a business invariant without I/O?
  Put it in `domain`.
- Does it call Postgres, filesystem, provider APIs, secrets, MCP, or settings?
  Put it in `infrastructure`.
- Does it describe a plugin/tool bundle loaded from disk?
  Put it in `plugins/`.

## Migration Plan

### Phase 1: Architecture Freeze

- Keep `ddd_layers_report` at zero.
- Add this document as the reference for new backend code.
- Do not rename `apps.backend` yet.

### Phase 2: Collections Tactical Refactor

- Define `Collection`, `CollectionItem`, `CollectionSlug`, `DataPath`.
- Define `CollectionRepository` and `AttachmentRepository`.
- Move dashboard projection orchestration into
  `application/collections/use_cases/`.
- Implement Postgres repositories under
  `infrastructure/persistence/postgres/`.

### Phase 3: Agent Runtime Tactical Refactor

- Define `AgentTask`, `AgentRun`, and `Artifact` domain objects.
- Move active-task resolution and run persistence into use cases.
- Replace broad `application/agent_runtime/dependencies.py` with smaller
  ports grouped by use case.

### Phase 4: Plugin Runtime Tactical Refactor

- Define `ToolDefinition`, `ToolPolicy`, `Capability`, and routing value
  objects.
- Separate registry scanning, policy resolution, execution, and logging.
- Keep plugin content in `plugins/tools/`.

### Phase 5: Model/RAG/Voice Contexts

- Model provider/catalog entities.
- Introduce RAG ingest use cases and ports.
- Introduce voice/media settings and quota policies as domain objects.

## Naming Rules

- `domain/<context>/entities.py`: aggregate roots and child entities.
- `domain/<context>/value_objects.py`: validated small types.
- `domain/<context>/policies.py`: pure decision functions/classes.
- `domain/<context>/repositories.py`: aggregate repository protocols.
- `application/<context>/commands/`: write-intent request objects.
- `application/<context>/queries/`: read-intent request objects.
- `application/<context>/dtos/`: response and transfer shapes owned by application workflows.
- `application/<context>/use_cases/`: handlers/workflows that orchestrate commands and queries.
- `application/<context>/ports.py`: non-aggregate external ports.
- `infrastructure/persistence/postgres/`: repository implementations.
- `infrastructure/<technical_area>/`: provider, settings, storage, runtime
  adapters.

## Anti-Patterns

- Importing `apps.backend.infrastructure.*` from `domain`.
- Putting FastAPI request models in domain modules.
- Creating an `Entity` class with no invariants just to look like DDD.
- Calling every external provider a repository.
- Moving files into `entities.py` before understanding aggregate boundaries.
- Renaming `apps.backend` before improving tactical boundaries.

## Definition Of Done

A DDD migration step is done when:

- `ddd_layers_report` is clean.
- The use case can be tested without real provider credentials.
- Domain tests do not require a DB pool.
- Repositories or ports are named after domain/application needs, not
  technical implementation details.
- Existing HTTP behavior remains compatible unless intentionally changed.
