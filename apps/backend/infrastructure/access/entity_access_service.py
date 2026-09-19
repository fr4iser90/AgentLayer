"""Single entry point for "may this actor do X to this entity".

Loads the facts (ownership, direct grant role, visibility, tenant grants) and
delegates the decision to the pure rules in ``domain/access/entity_access``.
Callers should not re-implement the SQL guards locally; the point of this module
is that there is one place to change when tenant-scoped entities arrive.

Composition is ``per-entity rule OR tenant layer``. The tenant layer only ever
adds access, and only for an entity whose ``visibility`` is ``tenant``, so a
private entity is decided exactly as it was before the tenant layer existed.

The tenant layer is keyed on the *entity's* tenant, read from the entity row
rather than from the caller. That is what makes a grant row unable to bridge two
tenants: a row naming another tenant's entity can never match.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from apps.backend.domain.access.entity_access import (
    EDIT,
    MANAGE,
    OWNED,
    PRIVATE,
    TENANT_VISIBLE,
    VIEW,
    evaluate_dashboard_access,
    evaluate_tenant_branch,
    evaluate_workspace_access,
)

logger = logging.getLogger(__name__)

WORKSPACE = "workspace"
DASHBOARD = "dashboard"

SUPPORTED_ENTITY_TYPES = (WORKSPACE, DASHBOARD)


def _uid(actor: Any) -> uuid.UUID | None:
    if isinstance(actor, uuid.UUID):
        return actor
    raw = getattr(actor, "id", None)
    if isinstance(raw, uuid.UUID):
        return raw
    if raw is not None:
        try:
            return uuid.UUID(str(raw))
        except (ValueError, TypeError):
            return None
    return None


def _norm(value: Any) -> str | None:
    return str(value or "").strip().lower() or None


def _load_workspace_facts(
    entity_id: str, uid: uuid.UUID, tenant_id: int
) -> dict[str, Any] | None:
    from apps.backend.infrastructure.db import db

    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT owner_user_id, access_role, visibility, tenant_id
                FROM project_workspaces
                WHERE id = %s AND tenant_id = %s
                """,
                (str(entity_id), tenant_id),
            )
            row = cur.fetchone()
    if row is None:
        return None
    return {
        "is_owner": str(row[0] or "") == str(uid),
        "access_role": _norm(row[1]),
        "visibility": _norm(row[2]) or PRIVATE,
        "tenant_id": int(row[3]),
    }


def _load_dashboard_facts(
    entity_id: str, uid: uuid.UUID, tenant_id: int
) -> dict[str, Any] | None:
    from apps.backend.infrastructure.db import db

    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT w.owner_user_id, m.role, w.visibility, w.tenant_id
                FROM user_dashboards w
                LEFT JOIN dashboard_members m
                  ON m.dashboard_id = w.id AND m.user_id = %s
                WHERE w.id = %s AND w.tenant_id = %s
                """,
                (uid, str(entity_id), tenant_id),
            )
            row = cur.fetchone()
    if row is None:
        return None
    return {
        "is_owner": str(row[0] or "") == str(uid),
        "member_role": _norm(row[1]),
        "visibility": _norm(row[2]) or PRIVATE,
        "tenant_id": int(row[3]),
    }


def _load_tenant_grants(
    entity_type: str, entity_id: str, tenant_id: int
) -> list[tuple[str, str]]:
    """(min_role, access) rows naming this entity, within the entity's tenant."""
    from apps.backend.infrastructure.db import db

    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT min_role, access FROM tenant_entity_grants
                WHERE entity_type = %s AND entity_id = %s AND tenant_id = %s
                """,
                (entity_type, str(entity_id), tenant_id),
            )
            rows = cur.fetchall()
    return [(str(r[0] or ""), str(r[1] or "")) for r in rows]


def tenant_layer_allows(
    entity_type: str,
    entity_id: str,
    actor: Any,
    tenant_id: int,
    needed: str = VIEW,
) -> bool:
    """Resolve just the tenant layer, for callers that already hold the entity.

    ``tenant_id`` must be the entity's own tenant. Passing the actor's tenant
    here is how a grant row ends up bridging two companies.
    """
    uid = _uid(actor)
    if uid is None or not entity_id or entity_type not in SUPPORTED_ENTITY_TYPES:
        return False
    from apps.backend.infrastructure.db import db

    tenant_role = db.user_membership_role(uid, tenant_id)
    grants = _load_tenant_grants(entity_type, entity_id, tenant_id)
    return evaluate_tenant_branch(
        tenant_role=tenant_role, grants=grants, needed=needed
    )


def can_access(
    entity_type: str,
    entity_id: str,
    actor: Any,
    needed: str = VIEW,
    tenant_id: int | None = None,
) -> bool:
    """Decide access for ``actor`` over ``entity_type``/``entity_id``.

    ``needed`` is one of ``view`` / ``edit`` / ``manage`` / ``owned``. Unknown
    entity types, missing actors and missing entities all deny.

    The entity is resolved only within the actor's tenant, so an entity that
    drifted into another tenant grants nothing even if the ownership columns
    still point at the actor. Pass ``tenant_id`` to skip the lookup when the
    caller already knows it.

    The tenant layer is consulted only when the per-entity rule denied and the
    entity is ``visibility='tenant'``, so a private entity costs one query and
    an owner never triggers it.
    """
    uid = _uid(actor)
    if uid is None or not entity_id:
        return False
    if entity_type not in SUPPORTED_ENTITY_TYPES:
        logger.debug("unsupported entity type for access decision: %s", entity_type)
        return False

    if tenant_id is None:
        from apps.backend.infrastructure.db import db

        tenant_id = int(db.user_tenant_id(uid) or 1)

    if entity_type == WORKSPACE:
        facts = _load_workspace_facts(entity_id, uid, tenant_id)
        if facts is None:
            return False
        if evaluate_workspace_access(
            is_owner=facts["is_owner"],
            access_role=facts["access_role"],
            needed=needed,
        ):
            return True
    else:
        facts = _load_dashboard_facts(entity_id, uid, tenant_id)
        if facts is None:
            return False
        if evaluate_dashboard_access(
            is_owner=facts["is_owner"],
            member_role=facts["member_role"],
            needed=needed,
        ):
            return True

    if facts["visibility"] != TENANT_VISIBLE:
        return False
    return tenant_layer_allows(
        entity_type, entity_id, uid, facts["tenant_id"], needed
    )


def can_access_workspace_row(
    row: Any, actor: Any, needed: str = VIEW, *, tenant_allows: bool = False
) -> bool:
    """Decide from an already-fetched ``project_workspaces`` row.

    Lets the ``fetch_*_workspace_row`` helpers keep their row-returning contract
    without re-fetching the row: fetch by id, then guard here.

    A row alone cannot answer the tenant question — the grants live in another
    table — so the caller passes ``tenant_allows``, normally from
    ``tenant_layer_allows``. Leaving it out keeps today's per-entity decision,
    which under-grants for a tenant-visible workspace: a tenant admin who
    ``can_access`` would let through is denied here.
    """
    if row is None:
        return False
    uid = _uid(actor)
    if uid is None:
        return False
    if evaluate_workspace_access(
        is_owner=str(row[1] or "") == str(uid),
        access_role=str(row[7] or "").strip().lower() or None,
        needed=needed,
    ):
        return True
    return bool(tenant_allows)


__all__ = [
    "DASHBOARD",
    "EDIT",
    "MANAGE",
    "OWNED",
    "SUPPORTED_ENTITY_TYPES",
    "VIEW",
    "WORKSPACE",
    "can_access",
    "can_access_workspace_row",
    "tenant_layer_allows",
]
