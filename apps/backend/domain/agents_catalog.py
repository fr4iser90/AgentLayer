"""Build agent catalog payloads for orchestrator tools (summary, not full admin dump)."""

from __future__ import annotations

from typing import Any

from apps.backend.domain.agent_access import is_elevated_role, user_may_invoke_agent
from apps.backend.domain.agent_registry import effective_tool_names_for_caller, get_agent_registry
from apps.backend.domain.embedded_subagent import DELEGATABLE_AGENT_IDS


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

    agents_out: list[dict[str, Any]] = []
    for aid in reg.agent_ids():
        if delegatable_only and aid not in DELEGATABLE_AGENT_IDS:
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
            "delegatable": aid in DELEGATABLE_AGENT_IDS,
            "invokable_by_caller": allowed,
        }
        if show_tools:
            row["tool_names"] = list(ag.get("tool_names") or [])
            row["effective_tool_names"] = effective_tool_names_for_caller(
                aid, user_role=role, tenant_id=tenant_id
            )
        agents_out.append(row)

    return {
        "ok": True,
        "agent_count": len(agents_out),
        "delegatable_agent_ids": sorted(DELEGATABLE_AGENT_IDS),
        "agents": agents_out,
        "note": (
            "Summary only (domains + capabilities). "
            + ("Full tool name lists included (admin)." if show_tools else "Call with include_tool_names=true as admin for tool lists.")
        ),
    }
