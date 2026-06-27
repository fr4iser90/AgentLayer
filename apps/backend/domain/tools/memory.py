"""
Tool / connection **memory** (planned).

Reserved for cross-request state that should **not** live inside individual tool modules:

- Retry backoff and last error class per ``service_key`` or tool name
- Last successful connection / preference hints for the Planner
- User overrides (e.g. default mailbox) — with explicit consent

Implementations will likely use Postgres (durable) and/or Redis (ephemeral). Nothing here is wired
yet; callers continue to rely on user secrets and tool outputs until this layer is implemented.
"""

from __future__ import annotations

# Placeholder for future: get_retry_hint(user_id, service_key) -> dict | None
