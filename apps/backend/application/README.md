# Backend Application Layer

Application services orchestrate use cases across domain rules and infrastructure adapters.

Use this layer for workflows that need persistence, provider clients, operator settings,
dashboard/media access, or other side effects. Keep `apps.backend.domain` focused on
pure decisions, policies, value objects, and port protocols.

Dependency direction:

- `api` may call `application`.
- `application` may call `domain` and infrastructure adapters.
- `domain` must not import `api`, `dashboard`, `infrastructure`, `integrations`, or `media`.
