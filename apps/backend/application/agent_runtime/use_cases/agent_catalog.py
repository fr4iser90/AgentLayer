"""Access-filtered, non-sensitive agent views for the chat UI (P2).

Kept in the application layer (not the api controller) so the site_role-based
elevation — which reads ``db.user_site_admin`` — stays out of the api layer,
which is forbidden from importing ``infrastructure``.
"""

from __future__ import annotations

from typing import Any

from apps.backend.domain.agent_runtime.access import user_may_invoke_agent
from apps.backend.domain.agent_runtime.registry import get_agent_registry

# Fields safe to expose to the chat UI picker. ``system_prompt`` and the raw
# tool-configuration (``tool_domains`` / ``tool_capability_any`` /
# ``tool_allowlist`` / ``tool_discipline_preset``) are intentionally omitted: the
# picker only needs identity + routing metadata, and those fields can carry
# instructions, secrets or allowlists that must not leak to a non-caller.
_PUBLIC_AGENT_KEYS: tuple[str, ...] = (
    "id",
    "name",
    "icon",
    "description",
    "min_role",
    "tool_domain",
    "tool_names",
    "requires_workspace",
    "execution_context",
    "model_profile",
)


def _agent_access_role(user: Any) -> str:
    """Agent-access role derived from the canonical ``site_role`` (P1), not legacy ``role``."""
    user_id = getattr(user, "id", None)
    if user_id is not None:
        try:
            from apps.backend.infrastructure.db import db

            site_flag = db.user_site_admin(user_id)
        except Exception:
            site_flag = None
        if site_flag is not None:
            return "admin" if site_flag else "user"
    return (getattr(user, "role", None) or "user").strip().lower() or "user"


def _public_agent_view(agent: dict[str, Any], invokable: bool) -> dict[str, Any]:
    """Thin, non-sensitive projection of an agent definition for the chat UI."""
    view: dict[str, Any] = {key: agent.get(key) for key in _PUBLIC_AGENT_KEYS if key in agent}
    if "external_runtime" in agent and (agent.get("external_runtime") or "").strip():
        view["external_runtime"] = agent.get("external_runtime") or None
    # Always true here: the list is pre-filtered to invokable agents. Kept for a
    # stable row shape / forward-compat if the endpoint ever returns the full
    # catalog annotated instead of filtered.
    view["invokable_by_caller"] = bool(invokable)
    return view


def list_invokable_agents(user: Any) -> list[dict[str, Any]]:
    """Agents the caller may invoke, projected to non-sensitive picker metadata."""
    role = _agent_access_role(user)
    user_id = getattr(user, "id", None)
    registry = get_agent_registry()
    agents_out: list[dict[str, Any]] = []
    for agent_id in registry.agent_ids():
        agent = registry.get_agent(agent_id)
        if not agent:
            continue
        allowed, _err = user_may_invoke_agent(role, agent_id, user_id=user_id)
        if not allowed:
            continue
        agents_out.append(_public_agent_view(agent, allowed))
    return agents_out


def get_invokable_agent(user: Any, agent_id: str) -> dict[str, Any] | None:
    """A single agent the caller may invoke, or ``None`` (to avoid enumeration)."""
    role = _agent_access_role(user)
    registry = get_agent_registry()
    agent = registry.get_agent(agent_id)
    if not agent:
        return None
    allowed, _err = user_may_invoke_agent(role, agent_id, user_id=getattr(user, "id", None))
    if not allowed:
        return None
    return _public_agent_view(agent, allowed)
