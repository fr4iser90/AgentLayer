"""Single entry point for "may this actor do X to this entity".

Loads the facts (ownership, direct grant role) and delegates the decision to the
pure rules in ``domain/access/entity_access``. Callers should not re-implement
the SQL guards locally; the point of this module is that there is one place to
change when tenant-scoped entities arrive.

Tenant-scoped grants are not wired yet — see the ``tenant`` seam below.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from apps.backend.domain.access.entity_access import (
    EDIT,
    MANAGE,
    OWNED,
    VIEW,
    evaluate_dashboard_access,
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


def _load_workspace_facts(
    entity_id: str, uid: uuid.UUID, tenant_id: int
) -> dict[str, Any] | None:
    from apps.backend.infrastructure.db import db

    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT owner_user_id, access_role FROM project_workspaces
                WHERE id = %s AND tenant_id = %s
                """,
                (str(entity_id), tenant_id),
            )
            row = cur.fetchone()
    if row is None:
        return None
    owner = row[0]
    return {
        "is_owner": str(owner or "") == str(uid),
        "access_role": str(row[1] or "").strip().lower() or None,
    }


def _load_dashboard_facts(
    entity_id: str, uid: uuid.UUID, tenant_id: int
) -> dict[str, Any] | None:
    from apps.backend.infrastructure.db import db

    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT w.owner_user_id, m.role
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
    owner = row[0]
    return {
        "is_owner": str(owner or "") == str(uid),
        "member_role": str(row[1] or "").strip().lower() or None,
    }


def can_access(
    entity_type: str,
    entity_id: str,
    actor: Any,
    needed: str = VIEW,
    tenant_id: int | None = None,
) -> bool:
    """Decide access for ``actor`` over ``entity_type``/``entity_id``.

    ``needed`` is one of ``view`` / ``edit`` / ``manage``. Unknown entity types,
    missing actors and missing entities all deny.

    The entity is resolved only within the actor's tenant, so an entity that
    drifted into another tenant grants nothing even if the ownership columns still
    point at the actor. Pass ``tenant_id`` to skip the lookup when the caller
    already knows it.
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
        return evaluate_workspace_access(
            is_owner=facts["is_owner"],
            access_role=facts["access_role"],
            needed=needed,
        )

    facts = _load_dashboard_facts(entity_id, uid, tenant_id)
    if facts is None:
        return False
    return evaluate_dashboard_access(
        is_owner=facts["is_owner"],
        member_role=facts["member_role"],
        needed=needed,
    )


def can_access_workspace_row(row: Any, actor: Any, needed: str = VIEW) -> bool:
    """Decide from an already-fetched ``project_workspaces`` row.

    Lets the ``fetch_*_workspace_row`` helpers keep their row-returning contract
    without a second query: fetch by id, then guard here.
    """
    if row is None:
        return False
    uid = _uid(actor)
    if uid is None:
        return False
    return evaluate_workspace_access(
        is_owner=str(row[1] or "") == str(uid),
        access_role=str(row[7] or "").strip().lower() or None,
        needed=needed,
    )


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
]
