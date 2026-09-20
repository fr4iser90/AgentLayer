"""Import-time wiring for the share adapter registry (ADR 0014 steps 2, 4).

Importing this module registers the adapters this deployment ships with and
injects the infrastructure each of them needs. Like the sibling ``*_service``
modules, the registration is a side effect of import so the domain layer
never has to know which infrastructure implementations are loaded.

A type that is not registered here is not readable through the generic
share path. That fails closed: an unregistered type can still be granted
(the write side is open on purpose), it just cannot be read — which is the
opposite of the pre-registry behaviour where a grant looked like access.

The calendar adapter's reader lives in ``plugins``. Injecting it here rather
than importing it from the domain keeps that direction one-way, and it is
also the single seam step 7 needs: swapping the live ICS fetch for a
published availability projection touches only ``read_shared_calendar``.
"""

from __future__ import annotations

import uuid
from typing import Any

from apps.backend.domain.shares.adapters import register_default_share_adapters
from apps.backend.domain.shares.adapters.calendar_adapter import (
    register_calendar_adapter_dependencies,
)


class _CalendarShareDeps:
    """Grants lookup plus the guarded calendar read."""

    def share_permission_get(
        self,
        *,
        owner_user_id: uuid.UUID,
        grantee_user_id: uuid.UUID,
        resource_type: str,
        resource_identifier: str,
    ) -> dict[str, Any] | None:
        from apps.backend.infrastructure.db.share_permissions_db import (
            share_permission_get,
        )

        return share_permission_get(
            owner_user_id, grantee_user_id, resource_type, resource_identifier
        )

    def read_shared_calendar(
        self, owner_user_id: uuid.UUID, *, days_ahead: int
    ) -> dict[str, Any]:
        from plugins.tools.personal.calendar.ics import fetch_shared_calendar

        return fetch_shared_calendar(owner_user_id, days_ahead=days_ahead)


register_calendar_adapter_dependencies(_CalendarShareDeps())
register_default_share_adapters()
