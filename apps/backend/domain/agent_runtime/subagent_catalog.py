from __future__ import annotations

import uuid
from typing import Protocol


class SubagentCatalogDependencies(Protocol):
    def user_role(self, user_id: uuid.UUID) -> str: ...

    def effective_string_list(self, key: str, *, tenant_id: int | None = None) -> list[str]: ...


_deps: SubagentCatalogDependencies | None = None


def register_subagent_catalog_dependencies(deps: SubagentCatalogDependencies) -> None:
    global _deps
    _deps = deps


def user_role(user_id: uuid.UUID) -> str:
    return _deps.user_role(user_id) if _deps is not None else ""


def effective_string_list(key: str, *, tenant_id: int | None = None) -> list[str]:
    return _deps.effective_string_list(key, tenant_id=tenant_id) if _deps is not None else []


def _delegatable_sets_from_registry() -> tuple[frozenset[str], frozenset[str]]:
    from apps.backend.domain.agent_runtime.registry import get_agent_registry

    reg = get_agent_registry()
    reg.ensure_loaded()
    standard: set[str] = set()
    admin_only: set[str] = set()
    for aid in reg.agent_ids():
        ag = reg.get_agent(aid) or {}
        if aid == "general":
            continue
        if ag.get("admin_only_delegatable"):
            admin_only.add(aid)
            continue
        if ag.get("delegatable"):
            standard.add(aid)
    return frozenset(standard), frozenset(admin_only)


def standard_delegatable_agent_ids() -> frozenset[str]:
    return _delegatable_sets_from_registry()[0]


def admin_only_delegatable_agent_ids() -> frozenset[str]:
    return _delegatable_sets_from_registry()[1]


def caller_is_admin(user_id: uuid.UUID | None) -> bool:
    if user_id is None:
        return False
    try:
        return (user_role(user_id) or "").strip().lower() == "admin"
    except Exception:
        return False


def effective_delegatable_agent_ids(
    *,
    caller_is_admin: bool = False,
    tenant_id: int | None = None,
) -> frozenset[str]:
    standard, admin_only = _delegatable_sets_from_registry()
    if caller_is_admin:
        base = standard | admin_only
    else:
        base = standard
    allowed = effective_string_list(
        "delegate.allowed_agent_ids",
        tenant_id=tenant_id,
    )
    if allowed:
        filt = frozenset(allowed)
        return base & filt
    return base


def build_delegate_agents_catalog_snippet(*, caller_is_admin: bool = False) -> str:
    """System-prompt block: which specialists exist and how to invoke them."""
    from apps.backend.domain.agent_runtime.registry import get_agent_registry

    reg = get_agent_registry()
    allowed_ids = effective_delegatable_agent_ids(caller_is_admin=caller_is_admin)
    lines = [
        "## Specialist sub-agents",
        "You cannot run shell, git push, or security_scan tools directly. "
        "When the user needs those capabilities, call **`delegate`** with "
        "`run_subagent: true`, a specialist `agent_id`, and a full `prompt`. "
        "Bind a workspace first (`create` / `bind`) — sub-agents inherit it (not required for operator). "
        "If `ssc_api_key` is listed as configured in the system context, do not ask the user to paste it.",
        "",
        "Available specialists:",
    ]
    for aid in sorted(allowed_ids):
        ag = reg.get_agent(aid)
        if not ag:
            continue
        name = ag.get("name") or aid
        desc = (ag.get("description") or "").strip().replace("\n", " ")
        if len(desc) > 240:
            desc = desc[:237] + "…"
        lines.append(f"- **{aid}** ({name}): {desc}")
    lines.append("")
    lines.append(
        "Pick the specialist by task (see descriptions above). "
        "For operator/platform settings (media library flags, interfaces): admins may "
        "`delegate` `agent_id=operator` — do not use coding for that. "
        "Pass `artifact_refs` when follow-up work needs prior sub-agent or tool outputs. "
        "Summarize the sub-agent result for the user (prefer `artifact_id` + short summary; "
        "do not paste raw `assistant_excerpt`). Use `task_*` tools for backlog."
    )
    return "\n".join(lines)


def __getattr__(name: str):
    if name == "DELEGATABLE_AGENT_IDS":
        return standard_delegatable_agent_ids()
    if name == "ADMIN_ONLY_DELEGATABLE_AGENT_IDS":
        return admin_only_delegatable_agent_ids()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "admin_only_delegatable_agent_ids",
    "build_delegate_agents_catalog_snippet",
    "caller_is_admin",
    "effective_delegatable_agent_ids",
    "standard_delegatable_agent_ids",
]
