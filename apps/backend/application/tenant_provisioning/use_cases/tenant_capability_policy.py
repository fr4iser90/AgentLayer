"""Per-tenant agent/tool capability limits from templates (Task 07+)."""

from __future__ import annotations

from typing import Any

from apps.backend.domain.tenant_templates.entities import TenantTemplate
from apps.backend.infrastructure.agent_runtime.agent_config_store import set_override
from apps.backend.infrastructure.agent_runtime.agent_config_effective import invalidate_agent_config_cache


def apply_template_capability_config(
    tenant_id: int,
    template: TenantTemplate,
    *,
    actor_user_id: Any | None = None,
) -> None:
    """Persist template agent/tool allowlists as tenant-scoped config overrides."""
    if template.enabled_agent_ids:
        agents = list(template.enabled_agent_ids)
        set_override(tenant_id, "chat.allowed_agent_ids", agents, user_id=actor_user_id)
        set_override(tenant_id, "delegate.allowed_agent_ids", agents, user_id=actor_user_id)
    if template.enabled_tool_domains:
        set_override(
            tenant_id,
            "tools.allowed_domains",
            list(template.enabled_tool_domains),
            user_id=actor_user_id,
        )
    if template.enabled_dashboard_kinds:
        set_override(
            tenant_id,
            "dashboards.allowed_kinds",
            list(template.enabled_dashboard_kinds),
            user_id=actor_user_id,
        )
    if template.enabled_nav_items:
        set_override(
            tenant_id,
            "ui.allowed_nav",
            list(template.enabled_nav_items),
            user_id=actor_user_id,
        )
    if template.enabled_dashboard_write_roles:
        set_override(
            tenant_id,
            "dashboards.write_membership_roles",
            list(template.enabled_dashboard_write_roles),
            user_id=actor_user_id,
        )
    invalidate_agent_config_cache(tenant_id)
