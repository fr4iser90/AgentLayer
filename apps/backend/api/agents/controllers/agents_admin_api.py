"""Admin API: agent registry overview (read-only)."""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from apps.backend.application.agent_runtime.use_cases.agent_governance_services import (
    assess_agent_prompt_risk,
    batch_upsert_user_agent_policies,
    create_agent_prompt_draft,
    delete_agent_access_policy,
    get_agent_prompt_version,
    list_agent_prompt_versions,
    list_agent_policy_rows,
    publish_agent_prompt_version,
    resolve_agent_governance,
    upsert_agent_access_policy,
)
from apps.backend.application.identity.use_cases.request_auth import (
    get_current_user,
    require_admin_capability,
    require_admin_scope,
)
from apps.backend.application.platform.use_cases.platform_controller_services import db
from apps.backend.domain.access.capabilities import AdminScope, AdminScopeError, CAP_AGENT_ASSIGN
from apps.backend.domain.agent_runtime.prompt_risk import (
    PromptRiskUnavailable,
    gate_enabled,
)
from apps.backend.domain.agent_runtime.registry import get_agent_registry


async def _scoped_tenant(request: Request, requested: int | None) -> tuple[AdminScope, int]:
    """Resolve which tenant an agent-policy action targets.

    Omitted means the caller's own tenant. An explicit value is only accepted
    inside the caller's scope — without that, a delegated ``agent.assign`` holder
    of company A could read and rewrite company B's agent policies.
    """
    scope = await require_admin_scope(request, CAP_AGENT_ASSIGN)
    tid = int(requested) if requested is not None else int(db.user_tenant_id(scope.actor_id) or 1)
    try:
        return scope, scope.require_tenant(tid, what="target tenant")
    except AdminScopeError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


async def _scoped_target_user_tenant(scope: AdminScope, user_id: uuid.UUID | None) -> None:
    """A policy written against a person must land in that person's tenant."""
    if user_id is None or scope.site_wide:
        return
    target_tenant = int(db.user_tenant_id(user_id) or 1)
    if not scope.allows_tenant(target_tenant):
        raise HTTPException(status_code=403, detail="user is outside your admin scope")

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


class AgentAccessBatchBody(BaseModel):
    """Grant/deny several agents to one person at once (P3, ``scope='user'``)."""

    user_id: uuid.UUID
    agent_ids: list[str] = Field(min_length=1)
    direct_state: str = Field(default="allow", pattern="^(inherit|allow|deny)$")
    delegate_state: str = Field(default="inherit", pattern="^(inherit|allow|deny)$")
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
    await require_admin_capability(request, CAP_AGENT_ASSIGN)
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
    # The store OR-joins its filters, so ``user_id`` is not bounded by the tenant
    # filter — the user behind it has to be checked separately.
    scope, tid = await _scoped_tenant(request, tenant_id)
    await _scoped_target_user_tenant(scope, user_id)
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
    scope, tid = await _scoped_tenant(request, tenant_id)
    await _scoped_target_user_tenant(scope, user_id)
    user = await get_current_user(request)
    reg = get_agent_registry()
    agent = reg.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")

    sim_role = (role or user.role or "admin").strip().lower()
    if sim_role not in ("admin", "user", "guest"):
        sim_role = "admin"

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
    _scope, tid = await _scoped_tenant(request, tenant_id)
    reg = get_agent_registry()
    if not reg.get_agent(agent_id):
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
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
    scope, tid = await _scoped_tenant(request, tenant_id)
    try:
        draft = create_agent_prompt_draft(
            tenant_id=tid,
            agent_id=agent_id,
            prompt_text=body.prompt_text,
            notes=body.notes,
            created_by=scope.actor_id,
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
    override_reason: str | None = Query(None, max_length=500),
) -> dict[str, Any]:
    """Publish a prompt version, gated by an LLM risk assessment.

    A ``high`` verdict blocks publish outright. Only a site admin may pass it,
    and only by supplying ``override_reason``, which is stored on the version
    alongside the verdict. If the assessment cannot be produced the publish is
    refused rather than waved through.
    """
    scope, tid = await _scoped_tenant(request, tenant_id)

    draft = await asyncio.to_thread(
        get_agent_prompt_version, tenant_id=tid, agent_id=agent_id, version_id=version_id
    )
    if not draft:
        raise HTTPException(status_code=404, detail="prompt version not found")

    risk_level = "unassessed"
    risk_reasons: list[str] = []
    override_by: uuid.UUID | None = None

    if gate_enabled():
        try:
            risk = await asyncio.to_thread(
                assess_agent_prompt_risk, draft.get("prompt_text") or "", agent_id=agent_id
            )
        except PromptRiskUnavailable as exc:
            raise HTTPException(
                status_code=503,
                detail=(
                    "prompt risk assessment unavailable — publish refused. "
                    f"({exc})"
                ),
            ) from exc
        risk_level = risk.level
        risk_reasons = list(risk.reasons)
        if risk.blocking:
            if not scope.site_wide:
                raise HTTPException(
                    status_code=403,
                    detail=(
                        "risk assessment rated this prompt high — publishing is "
                        "blocked. A site admin may override with override_reason."
                    ),
                    headers={"X-Prompt-Risk": "high"},
                )
            if not (override_reason or "").strip():
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "high-risk prompt: site admin override requires a "
                        "non-empty override_reason."
                    ),
                )
            override_by = scope.actor_id

    try:
        published = publish_agent_prompt_version(
            tenant_id=tid,
            agent_id=agent_id,
            version_id=version_id,
            published_by=scope.actor_id,
            risk_level=risk_level,
            risk_reasons=risk_reasons,
            override_by=override_by,
            override_reason=(override_reason or "").strip() or None,
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
    scope, tid = await _scoped_tenant(request, body.tenant_id)
    if body.scope == "global":
        try:
            scope.require_site_wide("global agent access policies")
        except AdminScopeError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
    await _scoped_target_user_tenant(scope, body.user_id)
    try:
        row = upsert_agent_access_policy(
            scope=body.scope,
            agent_id=agent_id,
            tenant_id=tid if body.scope in ("tenant", "user") else None,
            user_id=body.user_id,
            direct_state=body.direct_state,
            delegate_state=body.delegate_state,
            notes=body.notes,
            updated_by=scope.actor_id,
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
    # ``scope`` is the policy scope from the query string, so the admin scope
    # keeps its own name here.
    admin, tid = await _scoped_tenant(request, tenant_id)
    if scope == "global":
        try:
            admin.require_site_wide("global agent access policies")
        except AdminScopeError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
    await _scoped_target_user_tenant(admin, user_id)
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


@router.post("/v1/admin/agents/access-policy/batch")
async def admin_batch_agent_access_policy(
    request: Request,
    body: AgentAccessBatchBody,
) -> dict[str, Any]:
    """Grant/deny several agents to one person at once (P3, ``scope='user'``)."""
    scope = await require_admin_scope(request, CAP_AGENT_ASSIGN)
    await _scoped_target_user_tenant(scope, body.user_id)
    try:
        policies = batch_upsert_user_agent_policies(
            user_id=body.user_id,
            agent_ids=body.agent_ids,
            direct_state=body.direct_state,
            delegate_state=body.delegate_state,
            notes=body.notes,
            updated_by=scope.actor_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "policies": policies}
