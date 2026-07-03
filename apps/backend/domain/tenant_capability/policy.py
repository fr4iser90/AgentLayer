"""Per-tenant agent/tool capability limits (domain — no DB imports)."""

from __future__ import annotations

from typing import Protocol


class TenantCapabilityDependencies(Protocol):
    def config_string_list(self, tenant_id: int, knob_id: str) -> frozenset[str] | None: ...


_deps: TenantCapabilityDependencies | None = None


def register_tenant_capability_dependencies(deps: TenantCapabilityDependencies) -> None:
    global _deps
    _deps = deps


def tenant_chat_allowed_agent_ids(tenant_id: int) -> frozenset[str] | None:
    """When set, non-admin users may only invoke these agents in chat."""
    if _deps is None:
        return None
    return _deps.config_string_list(tenant_id, "chat.allowed_agent_ids")


def tenant_allowed_tool_domains(tenant_id: int) -> frozenset[str] | None:
    """When set, tools outside these domains (plus ``shared``) are hidden."""
    if _deps is None:
        return None
    return _deps.config_string_list(tenant_id, "tools.allowed_domains")


def tool_domain_allowed_for_tenant(tenant_id: int, domain: str | None) -> bool:
    allowed = tenant_allowed_tool_domains(tenant_id)
    if allowed is None:
        return True
    dom = (domain or "").strip().lower()
    if not dom or dom == "shared":
        return True
    return dom in allowed
