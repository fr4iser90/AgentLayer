"""Friend share grants for domain collections (cross-tenant)."""

from __future__ import annotations

import uuid
from typing import Any, Protocol

from apps.backend.domain.collections import db as col_db
from apps.backend.domain.shares.policy import grant_is_active

COLLECTION_RESOURCE_TYPE = "collection"


class CollectionGrantDependencies(Protocol):
    def share_permission_get(
        self,
        *,
        owner_user_id: uuid.UUID,
        grantee_user_id: uuid.UUID,
        resource_type: str,
        resource_identifier: str,
    ) -> dict[str, Any] | None: ...


_deps: CollectionGrantDependencies | None = None


def register_collection_grant_dependencies(deps: CollectionGrantDependencies) -> None:
    global _deps
    _deps = deps


def share_permission_get(
    *,
    owner_user_id: uuid.UUID,
    grantee_user_id: uuid.UUID,
    resource_type: str,
    resource_identifier: str,
) -> dict[str, Any] | None:
    if _deps is None:
        return None
    return _deps.share_permission_get(
        owner_user_id=owner_user_id,
        grantee_user_id=grantee_user_id,
        resource_type=resource_type,
        resource_identifier=resource_identifier,
    )


def grant_matches_collection(
    *,
    owner_user_id: uuid.UUID,
    slug: str,
    resource_identifier: str,
) -> bool:
    norm = col_db.normalize_slug(slug)
    if norm is None:
        return False
    ident = (resource_identifier or "").strip().lower()
    return ident == norm


def friend_collection_permission(
    grantee_user_id: uuid.UUID,
    owner_user_id: uuid.UUID,
    slug: str,
) -> dict[str, Any] | None:
    norm = col_db.normalize_slug(slug)
    if norm is None:
        return None
    grant = share_permission_get(
        owner_user_id=owner_user_id,
        grantee_user_id=grantee_user_id,
        resource_type=COLLECTION_RESOURCE_TYPE,
        resource_identifier=norm,
    )
    if not grant or not grant.get("is_allowed"):
        return None
    policy_raw = grant.get("policy") if isinstance(grant.get("policy"), dict) else {}
    if not grant_is_active(
        is_allowed=True,
        revoked_at=grant.get("revoked_at"),
        policy=policy_raw,
    ):
        return None
    return grant
