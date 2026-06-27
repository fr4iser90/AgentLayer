"""Infrastructure adapter for collection share permission lookups."""

from __future__ import annotations

import uuid
from typing import Any

from apps.backend.domain.collections import access as collection_access
from apps.backend.domain.shares import collection_grant
from apps.backend.infrastructure.db.share_permissions_db import share_permission_get


class _CollectionShareDeps:
    @staticmethod
    def share_permission_get(
        *,
        owner_user_id: uuid.UUID,
        grantee_user_id: uuid.UUID,
        resource_type: str,
        resource_identifier: str,
    ) -> dict[str, Any] | None:
        return share_permission_get(
            owner_user_id=owner_user_id,
            grantee_user_id=grantee_user_id,
            resource_type=resource_type,
            resource_identifier=resource_identifier,
        )


_deps = _CollectionShareDeps()
collection_access.register_collection_access_dependencies(_deps)
collection_grant.register_collection_grant_dependencies(_deps)

access_for_slug = collection_access.access_for_slug
friend_collection_permission = collection_grant.friend_collection_permission
grant_matches_collection = collection_grant.grant_matches_collection
resolve_collection = collection_access.resolve_collection
