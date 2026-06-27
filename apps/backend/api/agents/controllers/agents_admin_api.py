"""Admin API: agent registry overview (read-only)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request

from apps.backend.domain.agent_runtime.registry import effective_tool_names_for_caller, get_agent_registry
from apps.backend.application.identity.use_cases.request_auth import require_admin
from apps.backend.application.platform.use_cases.platform_controller_services import db

router = APIRouter(tags=["admin-agents"])


def _agent_admin_row(agent: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": agent.get("id"),
        "name": agent.get("name"),
        "icon": agent.get("icon"),
        "description": agent.get("description"),
        "min_role": agent.get("min_role"),
        "requires_workspace": bool(agent.get("requires_workspace")),
        "execution_context": agent.get("execution_context"),
        "model_profile": agent.get("model_profile"),
        "strict_workspace": bool(agent.get("strict_workspace")),
        "tool_discipline_preset": agent.get("tool_discipline_preset"),
        "tool_domains": agent.get("tool_domains") or [],
        "tool_capability_any": agent.get("tool_capability_any") or [],
        "tool_names_count": len(agent.get("tool_names") or []),
        "source_kind": agent.get("source_kind"),
        "source_path": agent.get("source_path"),
    }


@router.get("/v1/admin/agents")
async def admin_list_agents(request: Request) -> dict[str, Any]:
    """List agents with resolved tool counts (admin read-only)."""
    await require_admin(request)
    reg = get_agent_registry()
    rows = [_agent_admin_row(reg.get_agent(aid) or {}) for aid in reg.agent_ids()]
    return {"agents": rows}


@router.get("/v1/admin/agents/{agent_id}")
async def admin_get_agent(
    request: Request,
    agent_id: str,
    role: str | None = Query(None, description="Simulate effective tools for user or admin role"),
    tenant_id: int | None = Query(None, ge=1),
) -> dict[str, Any]:
    """Agent detail with resolved and effective tool names."""
    user = await require_admin(request)
    reg = get_agent_registry()
    agent = reg.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")

    sim_role = (role or user.role or "admin").strip().lower()
    if sim_role not in ("admin", "user", "guest"):
        sim_role = "admin"
    tid = int(tenant_id) if tenant_id is not None else int(db.user_tenant_id(user.id) or 1)

    payload = dict(agent)
    payload["effective_tool_names"] = effective_tool_names_for_caller(
        agent_id, user_role=sim_role, tenant_id=tid
    )
    payload["effective_preview"] = {"role": sim_role, "tenant_id": tid}
    return payload
