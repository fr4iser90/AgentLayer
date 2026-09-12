"""API endpoints for agent registry.

Thin wrappers: authentication comes from the application layer
(``request_auth``) and the access filtering + projection live in
``agent_catalog`` (application layer), so this controller never imports
``infrastructure`` (ddd_layers).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from typing import Any

from apps.backend.application.agent_runtime.use_cases.agent_catalog import (
    get_invokable_agent,
    list_invokable_agents,
)
from apps.backend.application.identity.use_cases.request_auth import get_current_user

router = APIRouter(tags=["agents"])


@router.get("/v1/agents")
async def list_agents(request: Request) -> list[dict[str, Any]]:
    """Agents the caller may invoke, projected to non-sensitive picker metadata."""
    user = await get_current_user(request)
    return list_invokable_agents(user)


@router.get("/v1/agents/{agent_id}")
async def get_agent(request: Request, agent_id: str) -> dict[str, Any]:
    """A single agent the caller may invoke (404 otherwise, to avoid enumeration)."""
    user = await get_current_user(request)
    agent = get_invokable_agent(user, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    return agent
