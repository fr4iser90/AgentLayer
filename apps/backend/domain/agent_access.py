"""Who may invoke which ``agent_id`` (product RBAC on top of ``AGENT_MIN_ROLE``)."""

from __future__ import annotations

ENDUSER_ALLOWED_AGENT_IDS = frozenset({"general"})


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


def user_may_invoke_agent(user_role: str | None, agent_id: str) -> tuple[bool, str]:
    """
    Return (allowed, error_message).
    Checks registry ``AGENT_MIN_ROLE`` and end-user allowlist (``general`` only).
    """
    aid = (agent_id or "").strip()
    if not aid:
        return True, ""

    from apps.backend.domain.agent_registry import get_agent_registry

    ag = get_agent_registry().get_agent(aid)
    if not ag:
        return False, f"Unknown agent {aid!r}."

    min_r = str(ag.get("min_role") or "user").strip().lower()
    if min_r == "admin" and not is_elevated_role(user_role):
        return False, "This agent is only available to admin users."

    if not is_elevated_role(user_role) and aid not in ENDUSER_ALLOWED_AGENT_IDS:
        return (
            False,
            "This agent is not available for your account. Use Chat with the General assistant.",
        )

    return True, ""
