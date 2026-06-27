"""Build agent catalog payloads for orchestrator tools (summary, not full admin dump)."""

from __future__ import annotations

from typing import Any

from apps.backend.domain.agent_runtime.registry import effective_tool_names_for_caller, get_agent_registry
from apps.backend.domain.agent_runtime.access import is_elevated_role, user_may_invoke_agent
from apps.backend.domain.agent_runtime.subagent_catalog import effective_delegatable_agent_ids


def build_agents_catalog(
    *,
    user_role: str | None,
    tenant_id: int,
    delegatable_only: bool = False,
    include_tool_names: bool = False,
) -> dict[str, Any]:
    """Summary catalog: domains + capabilities; tool names only when ``include_tool_names`` and admin."""
    reg = get_agent_registry()
    role = (user_role or "user").strip().lower()
    admin = is_elevated_role(role)
    show_tools = bool(include_tool_names and admin)
    delegatable_ids = effective_delegatable_agent_ids(caller_is_admin=admin)

    agents_out: list[dict[str, Any]] = []
    for aid in reg.agent_ids():
        if delegatable_only and aid not in delegatable_ids:
            continue
        ag = reg.get_agent(aid)
        if not ag:
            continue
        allowed, _err = user_may_invoke_agent(role, aid)
        row: dict[str, Any] = {
            "id": aid,
            "name": ag.get("name") or aid,
            "icon": ag.get("icon"),
            "description": (ag.get("description") or "").strip(),
            "min_role": ag.get("min_role") or "user",
            "requires_workspace": bool(ag.get("requires_workspace")),
            "tool_domains": list(ag.get("tool_domains") or []),
            "tool_capability_any": list(ag.get("tool_capability_any") or []),
            "tool_names_count": len(ag.get("tool_names") or []),
            "delegatable": aid in delegatable_ids,
            "invokable_by_caller": allowed,
        }
        # Orchestrator routing: specialists expose resolved tool names (allowlist-based agents
        # often have empty tool_domains). Full effective lists remain admin-only.
        if aid in delegatable_ids or show_tools:
            row["tool_names"] = list(ag.get("tool_names") or [])
        if show_tools:
            row["effective_tool_names"] = effective_tool_names_for_caller(
                aid, user_role=role, tenant_id=tenant_id
            )
        agents_out.append(row)

    return {
        "ok": True,
        "agent_count": len(agents_out),
        "delegatable_agent_ids": sorted(delegatable_ids),
        "agents": agents_out,
        "note": (
            "Specialists (delegatable) include tool_names for routing. "
            + (
                "Admin: effective_tool_names per agent when include_tool_names=true."
                if show_tools
                else "Call include_tool_names=true as admin for effective_tool_names."
            )
        ),
    }
