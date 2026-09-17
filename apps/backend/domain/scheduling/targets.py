"""Persisted scheduler job ``execution_target`` = registry ``agent_id`` (see ``plugins/agents``)."""

from __future__ import annotations

from typing import Any

EXECUTION_CODING = "coding"
EXECUTION_GENERAL = "general"


def _registry():
    from apps.backend.domain.agent_runtime.registry import get_agent_registry

    return get_agent_registry()


def normalize_execution_target(raw: str | None) -> str | None:
    if raw is None or not str(raw).strip():
        return None
    return str(raw).strip().lower()


def _agent_row(agent_id: str) -> dict[str, Any] | None:
    return _registry().get_agent(agent_id)


def is_agent_schedulable(agent_id: str) -> bool:
    agent = _agent_row(agent_id)
    if not agent:
        return False
    return bool(agent.get("schedulable", True))


def schedulable_agent_ids() -> list[str]:
    reg = _registry()
    out: list[str] = []
    for row in reg.list_agents():
        aid = str(row.get("id") or "").strip()
        if aid and is_agent_schedulable(aid):
            out.append(aid)
    return sorted(out)


def execution_target_catalog(
    *,
    user_role: str | None = None,
    user_id: Any | None = None,
    tenant_id: int | None = None,
) -> list[dict[str, Any]]:
    """Agents that may be stored in ``scheduler_jobs.execution_target``.

    Pass a caller (``user_id``) to get the targets that caller may actually invoke —
    the same ``user_may_invoke_agent`` check the create path and chat use — so the
    picker cannot offer a target that ``schedule_permission_error`` would reject.
    Without ``user_id`` this is the unfiltered registry view (admin surfaces).
    """
    from apps.backend.domain.agent_runtime.access import user_may_invoke_agent

    out: list[dict[str, Any]] = []
    for agent_id in schedulable_agent_ids():
        agent = _agent_row(agent_id)
        if not agent:
            continue
        if user_id is not None:
            allowed, _reason = user_may_invoke_agent(
                user_role, agent_id, tenant_id=tenant_id, user_id=user_id
            )
            if not allowed:
                continue
        name = str(agent.get("name") or agent_id)
        out.append(
            {
                "value": agent_id,
                "label": f"{name} ({agent_id})",
                "agent_id": agent_id,
                "requires_workspace": bool(agent.get("requires_workspace")),
                "min_role": str(agent.get("min_role") or "user"),
            }
        )
    return out


def is_valid_execution_target(raw: str | None) -> bool:
    t = normalize_execution_target(raw)
    return is_agent_schedulable(t) if t else False


def execution_target_error(_raw: str | None) -> str:
    allowed = ", ".join(schedulable_agent_ids()) or "(no schedulable agents)"
    return f"execution_target must be one of: {allowed}"


def agent_requires_workspace_for_target(raw: str | None) -> bool:
    t = normalize_execution_target(raw)
    if not t:
        return False
    agent = _agent_row(t)
    return bool(agent and agent.get("requires_workspace"))


def schedule_permission_error(
    *,
    user_role: str,
    execution_target: str,
    user_id: Any | None = None,
    tenant_id: int | None = None,
) -> str | None:
    """
    Return an HTTP/tool error message if the user may not create this schedule, else None.

    Feature access (``schedules_allowed``) is checked by callers via
    ``infrastructure.scheduling.schedules_access``; this covers the agent itself.

    Two layers, because ``min_role`` alone is not the whole answer:

    1. registry ``min_role`` — the hard admin gate;
    2. ``user_may_invoke_agent`` — the tenant allowlist (``chat.allowed_agent_ids``)
       and the ``agent_access_policies`` rows (global → tenant → user). Without this
       a schedule could reach an agent the caller is denied in chat.

    ``user_role`` must already reflect ``users.site_role`` — pass
    ``request_auth.agent_effective_role()``, not ``db.user_role()``, or the legacy
    ``role='admin'`` escalation reopens here.
    """
    t = normalize_execution_target(execution_target)
    if not t or not is_agent_schedulable(t):
        return execution_target_error(execution_target)
    agent = _agent_row(t)
    if not agent:
        return execution_target_error(execution_target)
    min_role = str(agent.get("min_role") or "user").strip().lower()
    role = str(user_role or "user").strip().lower()
    if min_role == "admin" and role != "admin":
        return f"execution_target {t} requires admin role"

    from apps.backend.domain.agent_runtime.access import user_may_invoke_agent

    allowed, reason = user_may_invoke_agent(role, t, tenant_id=tenant_id, user_id=user_id)
    if not allowed:
        detail = f": {reason}" if reason else ""
        return f"execution_target {t} is not available for your account{detail}"
    return None
