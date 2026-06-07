"""Resolve collection access for owner and friend share grantees."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Literal

from apps.backend.domain.collections import db as col_db
from apps.backend.domain.shares.policy import grant_is_active
from apps.backend.infrastructure.db.share_permissions_db import share_permission_get

CollectionRole = Literal["owner", "viewer", "editor"]


@dataclass(frozen=True)
class CollectionAccess:
    role: CollectionRole
    owner_user_id: uuid.UUID
    slug: str
    can_write: bool


def _policy_permission(policy: dict[str, Any]) -> str:
    perm = str(policy.get("permission") or "view").strip().lower()
    return perm if perm in ("view", "edit") else "view"


def access_for_slug(
    requesting_user_id: uuid.UUID,
    slug: str,
    *,
    owner_user_id: uuid.UUID | None = None,
) -> CollectionAccess | None:
    norm = col_db.normalize_slug(slug)
    if norm is None:
        return None

    owner = owner_user_id or requesting_user_id
    if owner == requesting_user_id:
        col = col_db.collection_get(requesting_user_id, norm)
        if col:
            return CollectionAccess("owner", requesting_user_id, norm, True)
        return None

    grant = share_permission_get(
        owner_user_id=owner,
        grantee_user_id=requesting_user_id,
        resource_type="collection",
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
    col = col_db.collection_get(owner, norm)
    if not col:
        return None
    policy = grant.get("policy") if isinstance(grant.get("policy"), dict) else {}
    perm = _policy_permission(policy)
    can_write = perm == "edit"
    role: CollectionRole = "editor" if can_write else "viewer"
    return CollectionAccess(role, owner, norm, can_write)


def resolve_collection(
    requesting_user_id: uuid.UUID,
    slug: str,
    *,
    owner_user_id: uuid.UUID | None = None,
    need_write: bool = False,
) -> tuple[CollectionAccess, dict[str, Any]] | tuple[None, str]:
    acc = access_for_slug(requesting_user_id, slug, owner_user_id=owner_user_id)
    if acc is None:
        return None, "collection not found or no access"
    if need_write and not acc.can_write:
        return None, "read-only access"
    col = col_db.collection_get(acc.owner_user_id, acc.slug)
    if not col:
        return None, "collection not found"
    return acc, col
