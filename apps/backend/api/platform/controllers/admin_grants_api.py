"""Admin API for tenant grants on workspaces and dashboards.

A grant says which tenant role may do what with one tenant-visible entity. The
access resolver gives ``tenant_admin``/``tenant_owner`` ``manage`` implicitly,
so grants are how a ``tenant_member`` ever reaches a company workspace.

Two invariants the handlers enforce together
------------------------------------------
The tenant a grant is written against is read from the **entity**, never taken
from the request. A body that carried ``tenant_id`` would let a company B admin
write a grant naming company A's tenant, and the reader keys on the entity's
tenant -- so that row would match A's members legitimately. Deriving the tenant
from the entity removes the attack rather than trying to validate it away.

The actor's admin scope is checked against that derived tenant before anything
is written. ``require_admin_scope`` says what kind of admin action is allowed;
``AdminScope.require_tenant`` says where it may reach. Both are needed: the
capability alone would let a delegated workspace admin act on any workspace.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from apps.backend.application.access.use_cases.grant_admin_service import (
    DASHBOARD,
    SUPPORTED_ENTITY_TYPES,
    WORKSPACE,
    GrantError,
    list_grants,
    replace_grants,
    resolve_scoped_tenant,
    revoke_grant,
)
from apps.backend.application.identity.use_cases.request_auth import require_admin_scope
from apps.backend.domain.access.capabilities import (
    CAP_DASHBOARD_MANAGE,
    CAP_WORKSPACE_MANAGE,
    AdminScope,
    AdminScopeError,
)
from apps.backend.domain.access.entity_access import GRANT_MIN_ROLES

router = APIRouter(prefix="/v1/admin/entity-grants", tags=["admin-grants"])

_CAPABILITY_BY_TYPE = {
    WORKSPACE: CAP_WORKSPACE_MANAGE,
    DASHBOARD: CAP_DASHBOARD_MANAGE,
}


class GrantEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    min_role: str = Field(..., max_length=32)
    access: str = Field(..., max_length=16)


class GrantsReplaceBody(BaseModel):
    """The complete intended grant set. Anything not listed is revoked."""

    model_config = ConfigDict(extra="forbid")
    grants: list[GrantEntry] = Field(default_factory=list)


def _norm_type(raw: str) -> str:
    et = str(raw or "").strip().lower()
    if et not in SUPPORTED_ENTITY_TYPES:
        raise HTTPException(
            status_code=404,
            detail=f"unsupported entity type: {raw}. Expected one of: "
            + ", ".join(SUPPORTED_ENTITY_TYPES),
        )
    return et


async def _scoped_entity(
    request: Request, entity_type: str, entity_id: str
) -> tuple[AdminScope, int]:
    """Resolve the entity's tenant and confirm the actor may act inside it.

    Returns the scope alongside the tenant so the handler records the actor from
    the same check that already passed with the right capability, rather than
    re-gating on a guessed one.

    The entity is resolved before the scope is consulted, so a missing entity is
    a 404 rather than a scope complaint about a tenant nobody named.
    """
    scope = await require_admin_scope(request, _CAPABILITY_BY_TYPE[entity_type])
    try:
        return scope, resolve_scoped_tenant(entity_type, entity_id, scope)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except AdminScopeError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except GrantError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{entity_type}/{entity_id}")
async def list_entity_grants(
    request: Request, entity_type: str, entity_id: str
) -> dict[str, Any]:
    """Every grant on one entity inside the actor's tenant."""
    et = _norm_type(entity_type)
    _scope, tenant_id = await _scoped_entity(request, et, entity_id)
    return {
        "entity_type": et,
        "entity_id": entity_id,
        "tenant_id": tenant_id,
        "grants": list_grants(et, entity_id, tenant_id),
    }


@router.put("/{entity_type}/{entity_id}")
async def replace_entity_grants(
    request: Request, entity_type: str, entity_id: str, body: GrantsReplaceBody
) -> dict[str, Any]:
    """Set the whole grant set for one entity. Omitted roles lose their grant.

    Replace rather than patch: a half-applied grant set is something nobody can
    reason about, so the caller states the full intent and it lands atomically.
    """
    et = _norm_type(entity_type)
    scope, tenant_id = await _scoped_entity(request, et, entity_id)
    try:
        written = replace_grants(
            entity_type=et,
            entity_id=entity_id,
            tenant_id=tenant_id,
            grants=[g.model_dump() for g in body.grants],
            created_by=scope.actor_id,
        )
    except GrantError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "grants": written}


@router.delete("/{entity_type}/{entity_id}/{min_role}")
async def revoke_entity_grant(
    request: Request, entity_type: str, entity_id: str, min_role: str
) -> dict[str, Any]:
    """Remove the grant for one minimum role."""
    et = _norm_type(entity_type)
    if str(min_role or "").strip().lower() not in GRANT_MIN_ROLES:
        raise HTTPException(
            status_code=400,
            detail="min_role must be one of: " + ", ".join(GRANT_MIN_ROLES),
        )
    _scope, tenant_id = await _scoped_entity(request, et, entity_id)
    try:
        removed = revoke_grant(
            entity_type=et,
            entity_id=entity_id,
            tenant_id=tenant_id,
            min_role=min_role,
        )
    except GrantError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "removed": removed}
