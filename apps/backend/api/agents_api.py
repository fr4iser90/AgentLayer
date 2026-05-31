"""API endpoints for agent registry."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from typing import Any

from apps.backend.domain.agent_registry import get_agent_registry

router = APIRouter(tags=["agents"])


@router.get("/v1/agents")
async def list_agents() -> list[dict[str, Any]]:
    """List all available agents."""
    registry = get_agent_registry()
    agents = registry.to_list_dict()
    return agents


@router.get("/v1/agents/{agent_id}")
async def get_agent(agent_id: str) -> dict[str, Any]:
    """Get a specific agent by ID."""
    registry = get_agent_registry()
    agent = registry.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    return agent