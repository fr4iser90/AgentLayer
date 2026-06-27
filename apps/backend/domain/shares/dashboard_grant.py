"""Resolve friend share grants for dashboard boards (cross-tenant)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal, NamedTuple, Protocol

from apps.backend.domain.shares.policy import grant_is_active

AccessRole = Literal["owner", "co_owner", "editor", "viewer"]


class DashboardAccessDetail(NamedTuple):
    """``allowed_block_ids`` is ``None`` for full dashboard (not granular)."""

    role: AccessRole | None
    allowed_block_ids: frozenset[str] | None
    granular_can_write: bool


class DashboardGrantDependencies(Protocol):
    def friend_dashboard_grant_rows(
        self,
        grantee_user_id: uuid.UUID,
        dashboard_id: uuid.UUID,
        resource_types: tuple[str, ...],
    ) -> list[dict[str, Any]]: ...

    def friend_shared_dashboard_rows(
        self,
        grantee_user_id: uuid.UUID,
        resource_types: tuple[str, ...],
    ) -> list[dict[str, Any]]: ...

    def dashboard_tenant_id(self, dashboard_id: uuid.UUID) -> int | None: ...


_deps: DashboardGrantDependencies | None = None


def register_dashboard_grant_dependencies(deps: DashboardGrantDependencies) -> None:
    global _deps
    _deps = deps

_DASHBOARD_RESOURCE_TYPES = ("dashboard",)


def _row_policy(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return dict(raw)
    return {}


def _policy_block_ids(policy: dict[str, Any]) -> frozenset[str] | None:
    raw = policy.get("block_ids")
    if not isinstance(raw, list):
        return None
    cleaned = [str(x).strip() for x in raw if str(x).strip()]
    return frozenset(cleaned) if cleaned else None


def _policy_permission(policy: dict[str, Any]) -> str:
    perm = str(policy.get("permission") or "view").strip().lower()
    return perm if perm in ("view", "edit") else "view"


def grant_matches_dashboard(
    *,
    dashboard_id: uuid.UUID,
    resource_type: str,
    resource_identifier: str,
    dashboard_kind: str,
) -> bool:
    ident = (resource_identifier or "primary").strip().lower()
    did = str(dashboard_id).strip().lower()
    return ident == did


def _access_from_policy(policy: dict[str, Any]) -> DashboardAccessDetail:
    perm = _policy_permission(policy)
    block_ids = _policy_block_ids(policy)
    if block_ids is not None:
        can_write = perm == "edit"
        role = "editor" if can_write else "viewer"
        return DashboardAccessDetail(role, block_ids, can_write)
    if perm == "edit":
        return DashboardAccessDetail("editor", None, False)
    return DashboardAccessDetail("viewer", None, False)


def friend_dashboard_access_detail(
    grantee_user_id: uuid.UUID,
    dashboard_id: uuid.UUID,
) -> DashboardAccessDetail | None:
    """Return access from an active friend share grant, or None."""
    rows = (
        _deps.friend_dashboard_grant_rows(
            grantee_user_id,
            dashboard_id,
            _DASHBOARD_RESOURCE_TYPES,
        )
        if _deps is not None
        else []
    )

    for row in rows:
        policy = _row_policy(row.get("policy"))
        if not grant_is_active(
            is_allowed=bool(row.get("is_allowed")),
            revoked_at=row.get("revoked_at"),
            policy=policy,
        ):
            continue
        if not grant_matches_dashboard(
            dashboard_id=dashboard_id,
            resource_type=str(row.get("resource_type") or ""),
            resource_identifier=str(row.get("resource_identifier") or ""),
            dashboard_kind=str(row.get("dashboard_kind") or ""),
        ):
            continue
        return _access_from_policy(policy)
    return None


def list_friend_shared_dashboards(grantee_user_id: uuid.UUID) -> list[dict[str, Any]]:
    """Dashboard summaries visible via friend share grants."""
    rows = (
        _deps.friend_shared_dashboard_rows(grantee_user_id, _DASHBOARD_RESOURCE_TYPES)
        if _deps is not None
        else []
    )

    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        wid = row.get("id")
        if not isinstance(wid, uuid.UUID):
            wid = uuid.UUID(str(wid))
        did = str(wid)
        if did in seen:
            continue
        policy = _row_policy(row.get("policy"))
        if not grant_is_active(is_allowed=True, revoked_at=None, policy=policy):
            continue
        if not grant_matches_dashboard(
            dashboard_id=wid,
            resource_type=str(row.get("resource_type") or ""),
            resource_identifier=str(row.get("resource_identifier") or ""),
            dashboard_kind=str(row.get("dashboard_kind") or ""),
        ):
            continue
        seen.add(did)
        access = _access_from_policy(policy)
        tpl = row.get("template_id")
        ua = row.get("updated_at")
        ca = row.get("created_at")
        out.append(
            {
                "id": did,
                "kind": row.get("kind") or "",
                "template_id": (tpl or "").strip() if isinstance(tpl, str) else None,
                "title": row.get("title") or "",
                "updated_at": ua.isoformat() if isinstance(ua, datetime) else str(ua or ""),
                "created_at": ca.isoformat() if isinstance(ca, datetime) else str(ca or ""),
                "access_role": access.role or "viewer",
                "access_via": "friend_share",
            }
        )
    return out


def dashboard_tenant_id(dashboard_id: uuid.UUID) -> int | None:
    return _deps.dashboard_tenant_id(dashboard_id) if _deps is not None else None
