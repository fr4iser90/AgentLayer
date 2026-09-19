"""Registry adapter for shared collections.

Wraps ``collection_grant`` unchanged. The projection is the grant dict the
getter returns — it carries the policy, which is what tells the caller the
grant is read-only or writable.
"""

from __future__ import annotations

import uuid
from typing import Any

from apps.backend.domain.collections import db as col_db
from apps.backend.domain.shares import collection_grant


class CollectionShareAdapter:
    resource_types: tuple[str, ...] = ("collection",)

    # The collection reader acts on ``permission`` and the expiry check in
    # the getter. ``block_ids`` is a dashboard concept and ``list_keys`` is
    # honoured by nothing today.
    policy_fields: frozenset[str] = frozenset({"permission", "expires_at"})

    supports_list: bool = False

    def normalize_identifier(self, raw: str) -> str | None:
        return col_db.normalize_slug(raw or "")

    def resolve(
        self,
        *,
        owner_user_id: uuid.UUID,
        grantee_user_id: uuid.UUID,
        identifier: str,
    ) -> Any | None:
        slug = self.normalize_identifier(identifier)
        if not slug:
            return None
        return collection_grant.friend_collection_permission(
            grantee_user_id, owner_user_id, slug
        )

    def list_shared(self, grantee_user_id: uuid.UUID) -> list[dict[str, Any]]:
        # No listing affordance on this adapter yet; the collection side
        # resolves by slug only.
        return []
