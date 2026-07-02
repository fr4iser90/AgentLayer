"""Who may invoke which ``agent_id`` (product RBAC on top of ``AGENT_MIN_ROLE``)."""

from __future__ import annotations

import uuid
from typing import Any, Protocol

ENDUSER_ALLOWED_AGENT_IDS = frozenset({"general", "knowledge_companion"})


class AgentAccessDependencies(Protocol):
    def list_agent_policies(
        self,
        *,
        tenant_id: int | None = None,
        user_id: uuid.UUID | None = None,
        agent_id: str | None = None,
    ) -> list[dict[str, Any]]: ...


_deps: AgentAccessDependencies | None = None


def register_agent_access_dependencies(deps: AgentAccessDependencies) -> None:
    global _deps
    _deps = deps


def normalize_user_role(role: str | None) -> str:
    r = (role or "user").strip().lower()
    if r in ("admin", "user", "guest"):
        return r
    return "user"


def is_elevated_role(role: str | None) -> bool:
    """Admins may use Build/Operator agents and full agent picker."""
    return normalize_user_role(role) == "admin"


def default_agent_for_workspace(user_role: str | None) -> str:
    """Bridge / workspace attach default when no explicit agent is set."""
    return "coding" if is_elevated_role(user_role) else "general"


def user_may_invoke_agent(
    user_role: str | None,
    agent_id: str,
    *,
    tenant_id: int | None = None,
    user_id: uuid.UUID | None = None,
) -> tuple[bool, str]:
    """
    Return (allowed, error_message).
    Checks registry ``AGENT_MIN_ROLE`` and end-user allowlist (``general`` only).
    """
    aid = (agent_id or "").strip()
    if not aid:
        return True, ""

    from apps.backend.domain.agent_runtime.registry import get_agent_registry

    ag = get_agent_registry().get_agent(aid)
    if not ag:
        return False, f"Unknown agent {aid!r}."

    min_r = str(ag.get("min_role") or "user").strip().lower()
    if min_r == "admin" and not is_elevated_role(user_role):
        return False, "This agent is only available to admin users."

    if _deps is not None:
        from apps.backend.domain.agent_runtime.governance import (
            AgentAccessPolicy,
            normalize_access_state,
            resolve_agent_access,
        )

        rows = _deps.list_agent_policies(
            tenant_id=tenant_id,
            user_id=user_id,
            agent_id=aid,
        )
        policies = [
            AgentAccessPolicy(
                scope=str(row.get("scope") or "global"),  # type: ignore[arg-type]
                tenant_id=int(row["tenant_id"]) if row.get("tenant_id") is not None else None,
                user_id=str(row["user_id"]) if row.get("user_id") is not None else None,
                agent_id=str(row.get("agent_id") or aid),
                direct_state=normalize_access_state(row.get("direct_state")),
                delegate_state=normalize_access_state(row.get("delegate_state")),
            )
            for row in rows
        ]
        decision = resolve_agent_access(agent=ag, user_role=user_role, policies=policies)
        if decision.direct_allowed:
            return True, ""
        return False, decision.direct_reason

    if not is_elevated_role(user_role) and aid not in ENDUSER_ALLOWED_AGENT_IDS:
        return (
            False,
            "This agent is not available for your account. Use Chat with the General assistant.",
        )

    return True, ""
