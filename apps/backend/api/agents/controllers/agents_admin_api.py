"""Admin API: agent registry overview (read-only)."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from apps.backend.application.agent_runtime.use_cases.agent_governance_services import (
    create_agent_prompt_draft,
    delete_agent_access_policy,
    list_agent_prompt_versions,
    list_agent_policy_rows,
    publish_agent_prompt_version,
    resolve_agent_governance,
    upsert_agent_access_policy,
)
from apps.backend.application.identity.use_cases.request_auth import require_admin
from apps.backend.application.platform.use_cases.platform_controller_services import db
from apps.backend.domain.agent_runtime.registry import get_agent_registry

router = APIRouter(tags=["admin-agents"])


class AgentAccessPolicyBody(BaseModel):
    scope: str = Field(pattern="^(global|tenant|user)$")
    tenant_id: int | None = Field(default=None, ge=1)
    user_id: uuid.UUID | None = None
    direct_state: str = Field(default="inherit", pattern="^(inherit|allow|deny)$")
    delegate_state: str = Field(default="inherit", pattern="^(inherit|allow|deny)$")
    notes: str | None = Field(default=None, max_length=2000)


class AgentPromptDraftBody(BaseModel):
    prompt_text: str = Field(min_length=1, max_length=12000)
    notes: str | None = Field(default=None, max_length=2000)


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


@router.get("/v1/admin/agents/policies")
async def admin_list_agent_policies(
    request: Request,
    tenant_id: int | None = Query(None, ge=1),
    user_id: uuid.UUID | None = Query(None),
    agent_id: str | None = Query(None),
) -> dict[str, Any]:
    user = await require_admin(request)
    tid = int(tenant_id) if tenant_id is not None else int(db.user_tenant_id(user.id) or 1)
    return {
        "policies": list_agent_policy_rows(
            tenant_id=tid,
            user_id=user_id,
            agent_id=agent_id,
        )
    }


@router.get("/v1/admin/agents/{agent_id}")
async def admin_get_agent(
    request: Request,
    agent_id: str,
    role: str | None = Query(None, description="Simulate effective tools for user or admin role"),
    tenant_id: int | None = Query(None, ge=1),
    user_id: uuid.UUID | None = Query(None),
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
    governance = resolve_agent_governance(
        agent_id=agent_id,
        user_role=sim_role,
        tenant_id=tid,
        user_id=user_id,
    )
    payload["effective_tool_names"] = governance["effective_tool_names"]
    payload["system_prompt"] = governance["system_prompt"]
    payload["effective_preview"] = {"role": sim_role, "tenant_id": tid}
    if user_id is not None:
        payload["effective_preview"]["user_id"] = str(user_id)
    payload["governance"] = governance
    return payload


@router.get("/v1/admin/agents/{agent_id}/prompt-versions")
async def admin_list_agent_prompt_versions(
    request: Request,
    agent_id: str,
    tenant_id: int | None = Query(None, ge=1),
    limit: int = Query(20, ge=1, le=100),
) -> dict[str, Any]:
    user = await require_admin(request)
    reg = get_agent_registry()
    if not reg.get_agent(agent_id):
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    tid = int(tenant_id) if tenant_id is not None else int(db.user_tenant_id(user.id) or 1)
    return {
        "versions": list_agent_prompt_versions(
            tenant_id=tid,
            agent_id=agent_id,
            limit=limit,
        )
    }


@router.post("/v1/admin/agents/{agent_id}/prompt-drafts")
async def admin_create_agent_prompt_draft(
    request: Request,
    agent_id: str,
    body: AgentPromptDraftBody,
    tenant_id: int | None = Query(None, ge=1),
) -> dict[str, Any]:
    user = await require_admin(request)
    tid = int(tenant_id) if tenant_id is not None else int(db.user_tenant_id(user.id) or 1)
    try:
        draft = create_agent_prompt_draft(
            tenant_id=tid,
            agent_id=agent_id,
            prompt_text=body.prompt_text,
            notes=body.notes,
            created_by=user.id,
        )
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found") from None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "version": draft}


@router.post("/v1/admin/agents/{agent_id}/prompt-versions/{version_id}/publish")
async def admin_publish_agent_prompt_version(
    request: Request,
    agent_id: str,
    version_id: uuid.UUID,
    tenant_id: int | None = Query(None, ge=1),
) -> dict[str, Any]:
    user = await require_admin(request)
    tid = int(tenant_id) if tenant_id is not None else int(db.user_tenant_id(user.id) or 1)
    try:
        published = publish_agent_prompt_version(
            tenant_id=tid,
            agent_id=agent_id,
            version_id=version_id,
            published_by=user.id,
        )
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found") from None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "version": published}


@router.put("/v1/admin/agents/{agent_id}/access-policy")
async def admin_put_agent_access_policy(
    request: Request,
    agent_id: str,
    body: AgentAccessPolicyBody,
) -> dict[str, Any]:
    user = await require_admin(request)
    tid = int(body.tenant_id) if body.tenant_id is not None else int(db.user_tenant_id(user.id) or 1)
    try:
        row = upsert_agent_access_policy(
            scope=body.scope,
            agent_id=agent_id,
            tenant_id=tid if body.scope in ("tenant", "user") else None,
            user_id=body.user_id,
            direct_state=body.direct_state,
            delegate_state=body.delegate_state,
            notes=body.notes,
            updated_by=user.id,
        )
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found") from None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "policy": row}


@router.delete("/v1/admin/agents/{agent_id}/access-policy")
async def admin_delete_agent_access_policy(
    request: Request,
    agent_id: str,
    scope: str = Query(..., pattern="^(global|tenant|user)$"),
    tenant_id: int | None = Query(None, ge=1),
    user_id: uuid.UUID | None = Query(None),
) -> dict[str, Any]:
    user = await require_admin(request)
    tid = int(tenant_id) if tenant_id is not None else int(db.user_tenant_id(user.id) or 1)
    try:
        deleted = delete_agent_access_policy(
            scope=scope,
            agent_id=agent_id,
            tenant_id=tid if scope == "tenant" else None,
            user_id=user_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "deleted": deleted}
