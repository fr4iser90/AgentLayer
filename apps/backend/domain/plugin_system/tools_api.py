"""HTTP routes for tool schemas and tool registry admin (no per-tool hardcoding)."""

from __future__ import annotations

import json
import logging
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from apps.backend.infrastructure.auth import require_admin, require_permission
from apps.backend.domain.plugin_system.capability_index import (
    build_capability_index,
    list_tools_without_capabilities,
)
from apps.backend.domain.plugin_system.registry import get_registry, reload_registry
from apps.backend.domain.plugin_system.tool_policy import (
    attach_execution_context_by_tool,
    enrich_meta_for_admin,
    filter_chat_tool_specs,
    filter_tools_meta,
)
from apps.backend.domain.http_identity import resolve_tools_list_identity
from apps.backend.infrastructure.db import db
from apps.backend.infrastructure.public_error import http_500_detail

logger = logging.getLogger(__name__)

router = APIRouter()


def _policies_map_safe() -> dict[tuple[str, str], dict[str, Any]]:
    try:
        from apps.backend.infrastructure.tool_operator_policy_db import policies_map

        return policies_map()
    except Exception:
        logger.debug("tool policy map unavailable", exc_info=True)
        return {}


def _registered_function_name(spec: dict) -> str | None:
    fn = spec.get("function") if isinstance(spec, dict) else None
    if isinstance(fn, dict):
        n = fn.get("name")
        return str(n) if n else None
    return None


@router.get("/v1/capabilities")
async def list_capabilities(request: Request):
    """
    Machine-readable capability index (ADR 0001): ``capability`` → tools that declare it.

    Built from the same policy-filtered ``tools_meta`` as ``GET /v1/tools`` for this caller.
    """
    reg = get_registry()
    pmap = _policies_map_safe()
    uid, tid = resolve_tools_list_identity(request)
    role = db.user_role(uid)
    meta = filter_tools_meta(reg.tools_meta, pmap, role, tid)
    by_cap = build_capability_index([dict(m) for m in meta])
    uncl = list_tools_without_capabilities([dict(m) for m in meta])
    return {
        "schema_version": 1,
        "by_capability": by_cap,
        "tools_unclassified": uncl,
    }


@router.get("/v1/tools")
async def list_tools(request: Request):
    """Chat ``tools[]``-shaped specs plus registry metadata; respects operator policy and caller access."""
    reg = get_registry()
    pmap = _policies_map_safe()
    uid, tid = resolve_tools_list_identity(request)
    role = db.user_role(uid)
    tools = filter_chat_tool_specs(reg.chat_tool_specs, reg, pmap, role, tid)
    meta = [dict(m) for m in filter_tools_meta(reg.tools_meta, pmap, role, tid)]
    attach_execution_context_by_tool(meta, pmap)
    return {"tools": tools, "tools_meta": meta}


@router.get("/v1/router/categories")
async def list_router_categories():
    """Router category ids (from each module's ``TOOL_DOMAIN``) for operator UIs and .env presets."""
    reg = get_registry()
    return {"categories": reg.list_router_categories_catalog()}


@router.get("/v1/admin/tools")
async def admin_list_tools(request: Request):
    """Tool metadata plus operator policy rows (effective flags for admin UI)."""
    await require_admin(request)
    reg = get_registry()
    pmap = _policies_map_safe()
    try:
        from apps.backend.infrastructure.tool_operator_policy_db import list_policies

        rows = list_policies()
    except Exception:
        logger.debug("list_policies failed", exc_info=True)
        rows = []
    return {
        "tools": enrich_meta_for_admin(reg.tools_meta, pmap),
        "policy_rows": rows,
    }


@router.post("/v1/admin/reload-tools")
@require_permission("write", "tool")
async def admin_reload_tools(request: Request, user, scope: Literal["all", "extra"] = "all"):
    """
    Rescan all configured tool directories (``AGENT_TOOL_DIRS`` or defaults).
    Broken or conflicting tools are skipped with logs. ``scope`` is accepted for API
    compatibility; both values perform the same full rescan.
    """
    try:
        reg = reload_registry(scope=scope)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.exception("reload-tools failed")
        raise HTTPException(status_code=500, detail=http_500_detail(e)) from e
    names = [_registered_function_name(t) for t in reg.chat_tool_specs]
    pmap = _policies_map_safe()
    tools = enrich_meta_for_admin(reg.tools_meta, pmap)
    return {
        "ok": True,
        "scope": scope,
        "tools": tools,
        "tool_count": len(reg.chat_tool_specs),
        "tool_names": [n for n in names if n],
    }


class ToolPolicyItem(BaseModel):
    package_id: str = Field(..., min_length=1)
    tool_name: str = "*"
    enabled: bool = True
    min_role: Literal["user", "admin"] = "user"
    allowed_tenant_ids: list[int] | None = None
    execution_context: str | None = None


class ToolPoliciesPutBody(BaseModel):
    policies: list[ToolPolicyItem]


@router.put("/v1/admin/tool-policies")
async def admin_put_tool_policies(request: Request, body: ToolPoliciesPutBody):
    """Replace operator tool policy table (admin)."""
    await require_admin(request)
    try:
        from apps.backend.infrastructure.tool_operator_policy_db import replace_all_policies

        replace_all_policies([p.model_dump() for p in body.policies])
    except Exception as e:
        logger.exception("tool-policies save failed")
        raise HTTPException(status_code=500, detail=http_500_detail(e)) from e
    return {"ok": True, "count": len(body.policies)}


@router.post("/v1/admin/create-tool")
@require_permission("write", "tool")
async def admin_create_tool(request: Request, user):
    """
    Same JSON body as the chat tool ``create`` (codegen without ``source``, or full module in ``source``).
    """
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="invalid JSON body") from None
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="JSON object expected")

    from plugins.tools.platform.tool_factory.create import create as run_create_tool

    raw = run_create_tool(body)
    try:
        out = json.loads(raw)
    except json.JSONDecodeError:
        logger.exception("create-tool returned non-JSON: %s", raw[:500])
        raise HTTPException(status_code=500, detail="create-tool returned invalid JSON") from None
    return out
