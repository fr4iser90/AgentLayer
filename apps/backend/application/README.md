# Backend Application Layer

Application services orchestrate use cases across domain rules and infrastructure adapters.

Use this layer for workflows that need persistence, provider clients, operator settings,
dashboard/media access, or other side effects. Keep `apps.backend.domain` focused on
pure decisions, policies, value objects, and port protocols.

Dependency direction:

- `api` may call `application`.
- `application` may call `domain` and infrastructure adapters.
- `domain` must not import `api`, `dashboard`, `infrastructure`, `integrations`, or `media`.

## Package Shape

Each bounded context should follow the same small shape:

```text
application/<context>/
  commands/
  queries/
  dtos/
  ports.py
  use_cases/
```

Use `commands/` for write-intent request objects, `queries/` for read-intent
request objects, and `dtos/` for application response shapes. Use `ports.py`
for application-level protocols needed by use cases. Use `use_cases/` for
handlers/workflows that coordinate domain rules with repositories, providers,
transactions, or other side effects.

New workflows enter through this layer directly. Move call sites to canonical
application, domain, or infrastructure modules before removing legacy paths.
