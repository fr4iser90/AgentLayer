"""Per-tenant agent/tool/dashboard/UI capability limits (domain — no DB imports)."""

from __future__ import annotations

from typing import Protocol

# Well-known first-party nav ids (UI filters when ``ui.allowed_nav`` is set).
KNOWN_NAV_ITEMS: frozenset[str] = frozenset(
    {"home", "chat", "studio", "dashboard", "schedules", "tasks", "shares"}
)


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


def tenant_allowed_dashboard_kinds(tenant_id: int) -> frozenset[str] | None:
    """
    When set, gallery create/list is limited to these dashboard kinds.
    ``None`` means unrestricted (typical default tenants).
    """
    if _deps is None:
        return None
    return _deps.config_string_list(tenant_id, "dashboards.allowed_kinds")


def dashboard_kind_allowed_for_tenant(tenant_id: int, kind: str | None) -> bool:
    allowed = tenant_allowed_dashboard_kinds(tenant_id)
    if allowed is None:
        return True
    k = (kind or "").strip().lower()
    return bool(k) and k in allowed


def tenant_allowed_nav_items(tenant_id: int) -> frozenset[str] | None:
    """
    When set, first-party chrome is limited to these nav ids.
    ``None`` means full consumer nav.
    """
    if _deps is None:
        return None
    raw = _deps.config_string_list(tenant_id, "ui.allowed_nav")
    if raw is None:
        return None
    return frozenset(x for x in raw if x in KNOWN_NAV_ITEMS) or None


_WRITE_MEMBERSHIP_ROLES = frozenset({"tenant_owner", "tenant_admin", "tenant_member"})


def tenant_dashboard_write_membership_roles(tenant_id: int) -> frozenset[str] | None:
    """
    When set, only these tenant membership roles may create/edit dashboard structure.
    ``None`` means unrestricted (current default).
    """
    if _deps is None:
        return None
    raw = _deps.config_string_list(tenant_id, "dashboards.write_membership_roles")
    if raw is None:
        return None
    cleaned = frozenset(x for x in raw if x in _WRITE_MEMBERSHIP_ROLES)
    return cleaned or None


def tenant_can_structure_edit_dashboards(tenant_id: int, membership_role: str | None) -> bool:
    allowed = tenant_dashboard_write_membership_roles(tenant_id)
    if allowed is None:
        return True
    role = (membership_role or "").strip().lower()
    return role in allowed