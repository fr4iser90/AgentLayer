from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

AccessState = Literal["inherit", "allow", "deny"]
AccessScope = Literal["global", "tenant", "user"]


@dataclass(frozen=True)
class AgentAccessPolicy:
    scope: AccessScope
    agent_id: str
    direct_state: AccessState = "inherit"
    delegate_state: AccessState = "inherit"
    tenant_id: int | None = None
    user_id: str | None = None


@dataclass(frozen=True)
class AgentAccessDecision:
    agent_id: str
    direct_allowed: bool
    delegate_allowed: bool
    direct_reason: str
    delegate_reason: str
    direct_source: str
    delegate_source: str


def normalize_access_state(value: str | None) -> AccessState:
    state = (value or "inherit").strip().lower()
    if state in ("allow", "deny", "inherit"):
        return state  # type: ignore[return-value]
    return "inherit"


def _is_elevated_role(role: str | None) -> bool:
    return (role or "user").strip().lower() == "admin"


def _base_direct(agent: dict, *, user_role: str | None) -> tuple[bool, str]:
    aid = str(agent.get("id") or "").strip()
    if not aid:
        return False, "unknown agent"
    min_role = str(agent.get("min_role") or "user").strip().lower()
    if min_role == "admin" and not _is_elevated_role(user_role):
        return False, "agent requires admin role"
    if _is_elevated_role(user_role):
        return True, "admin role may invoke registered agents"
    if aid == "general":
        return True, "general assistant is available by default"
    return False, "direct access is not available by default for this role"


def _base_delegate(agent: dict, *, user_role: str | None) -> tuple[bool, str]:
    aid = str(agent.get("id") or "").strip()
    if not aid or aid == "general":
        return False, "agent is not a delegatable specialist"
    if agent.get("admin_only_delegatable"):
        if _is_elevated_role(user_role):
            return True, "admin-only specialist is delegatable by admins"
        return False, "specialist delegation requires admin role"
    if agent.get("delegatable"):
        return True, "specialist is delegatable by default"
    return False, "agent is not marked delegatable"


def _apply_state(
    *,
    base_allowed: bool,
    base_reason: str,
    policies: list[AgentAccessPolicy],
    field: Literal["direct_state", "delegate_state"],
    hard_denied: bool,
) -> tuple[bool, str, str]:
    allowed = base_allowed
    reason = base_reason
    source = "registry_default"
    if hard_denied:
        return allowed, reason, source
    for policy in policies:
        state = getattr(policy, field)
        if state == "inherit":
            continue
        allowed = state == "allow"
        source = f"{policy.scope}_policy"
        reason = f"{field.removesuffix('_state')} access {state}ed by {policy.scope} policy"
    return allowed, reason, source


def resolve_agent_access(
    *,
    agent: dict,
    user_role: str | None,
    policies: list[AgentAccessPolicy],
) -> AgentAccessDecision:
    aid = str(agent.get("id") or "").strip()
    direct_base, direct_reason = _base_direct(agent, user_role=user_role)
    delegate_base, delegate_reason = _base_delegate(agent, user_role=user_role)
    min_role = str(agent.get("min_role") or "user").strip().lower()
    direct_hard_denied = min_role == "admin" and not _is_elevated_role(user_role)
    direct_allowed, direct_reason, direct_source = _apply_state(
        base_allowed=direct_base,
        base_reason=direct_reason,
        policies=policies,
        field="direct_state",
        hard_denied=direct_hard_denied,
    )
    delegate_allowed, delegate_reason, delegate_source = _apply_state(
        base_allowed=delegate_base,
        base_reason=delegate_reason,
        policies=policies,
        field="delegate_state",
        hard_denied=False,
    )
    return AgentAccessDecision(
        agent_id=aid,
        direct_allowed=direct_allowed,
        delegate_allowed=delegate_allowed,
        direct_reason=direct_reason,
        delegate_reason=delegate_reason,
        direct_source=direct_source,
        delegate_source=delegate_source,
    )
