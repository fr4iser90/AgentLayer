"""Registry adapter for shared dashboards.

Wraps ``dashboard_grant`` unchanged. The projection is the existing
``DashboardAccessDetail`` named tuple — role, the block ids the grant
restricts to, and whether the grantee may write.
"""

from __future__ import annotations

import uuid
from typing import Any

from apps.backend.domain.shares import dashboard_grant


class DashboardShareAdapter:
    resource_types: tuple[str, ...] = ("dashboard",)

    # What the dashboard reader actually acts on. ``days_ahead`` and
    # ``list_keys`` are accepted by the global policy validator but mean
    # nothing here — declaring only the honoured set is what lets step 3
    # reject the rest at write time (ADR 0014 §1.9).
    policy_fields: frozenset[str] = frozenset(
        {"permission", "block_ids", "expires_at"}
    )

    supports_list: bool = True

    def normalize_identifier(self, raw: str) -> str | None:
        text = (raw or "").strip().lower()
        if not text:
            return None
        try:
            return str(uuid.UUID(text))
        except ValueError:
            return None

    def resolve(
        self,
        *,
        owner_user_id: uuid.UUID,
        grantee_user_id: uuid.UUID,
        identifier: str,
        request: dict[str, Any] | None = None,
    ) -> Any | None:
        # The dashboard projection is not horizon-scoped; ``request`` is
        # accepted for protocol conformance and deliberately unused.
        dashboard_id = self.normalize_identifier(identifier)
        if dashboard_id is None:
            return None
        return dashboard_grant.friend_dashboard_access_detail(
            grantee_user_id, uuid.UUID(dashboard_id)
        )

    def list_shared(self, grantee_user_id: uuid.UUID) -> list[dict[str, Any]]:
        return dashboard_grant.list_friend_shared_dashboards(grantee_user_id)
