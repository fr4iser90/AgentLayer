"""Application façade over the grant writer.

The HTTP layer may not reach into ``infrastructure`` directly, so the grant
operations the admin API needs are surfaced here. The rules themselves live in
:mod:`apps.backend.infrastructure.access.tenant_grants` and
:mod:`apps.backend.domain.access.entity_access`; this adds no policy of its
own — it only decides which of them a use case is made of.
"""

from __future__ import annotations

import uuid
from typing import Any

from apps.backend.infrastructure.access.entity_access_service import (
    DASHBOARD,
    SUPPORTED_ENTITY_TYPES,
    WORKSPACE,
)
from apps.backend.infrastructure.access.tenant_grants import (
    GrantError,
    entity_tenant,
    list_grants,
    replace_grants,
    revoke_grant,
    upsert_grant,
)

__all__ = [
    "DASHBOARD",
    "GrantError",
    "SUPPORTED_ENTITY_TYPES",
    "WORKSPACE",
    "entity_tenant",
    "list_grants",
    "replace_grants",
    "revoke_grant",
    "upsert_grant",
    "resolve_scoped_tenant",
]


def resolve_scoped_tenant(
    entity_type: str, entity_id: str, scope: Any
) -> int:
    """The entity's tenant, after the actor's admin scope has cleared it.

    Kept here so the order is fixed in one place: read the tenant from the
    entity, then ask the scope about *that* value. A handler that asked the
    scope about a tenant taken from the request would be checking the wrong
    thing and would pass.

    Raises ``GrantError`` for an unusable entity type, ``LookupError`` when the
    entity does not exist, and whatever ``AdminScope.require_tenant`` raises
    when the tenant is out of reach.
    """
    tid = entity_tenant(entity_type, entity_id)
    if tid is None:
        raise LookupError(f"{entity_type} not found")
    return scope.require_tenant(tid, what=entity_type)
