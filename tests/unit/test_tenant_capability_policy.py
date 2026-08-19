"""Tenant template capability allowlists."""

from __future__ import annotations

from unittest.mock import patch

from apps.backend.application.tenant_provisioning.use_cases import tenant_capability_policy as cap
from apps.backend.application.tenant_provisioning.use_cases.tenant_template_loader import (
    get_template,
    load_all_templates,
)
from apps.backend.domain.tenant_capability import policy as tenant_cap
from apps.backend.domain.tenant_templates.entities import TenantTemplate


class _FakeCapabilityDeps:
    def __init__(self, values: dict[str, frozenset[str]] | None = None) -> None:
        self._values = values or {}

    def config_string_list(self, tenant_id: int, knob_id: str) -> frozenset[str] | None:
        return self._values.get(knob_id)


def test_public_ops_hub_template_has_nav_allowlist() -> None:
    tpl = get_template("tpl_ops_hub")
    assert "dashboard" in tpl.enabled_nav_items
    assert "studio" not in tpl.enabled_nav_items


def test_private_vertical_template_optional() -> None:
    """Operator-local templates under content/_private/tenant-templates/ may exist."""
    templates = load_all_templates(reload=True)
    assert "tpl_default_ops" in templates
    assert "tpl_ops_hub" in templates


def test_apply_template_capability_config_writes_overrides() -> None:
    tpl = TenantTemplate(
        id="t",
        name="T",
        description="",
        vertical_profile="default_ops",
        departments=(),
        profession_roles=(),
        workflow_defaults={},
        seed_content_glob=None,
        enabled_agent_ids=("general", "knowledge_companion"),
        enabled_tool_domains=("rag", "shared"),
        enabled_dashboard_kinds=("projects",),
        enabled_nav_items=("home", "chat", "dashboard"),
        enabled_dashboard_write_roles=("tenant_admin", "tenant_owner"),
    )
    with (
        patch.object(cap, "set_override") as set_ov,
        patch.object(cap, "invalidate_agent_config_cache") as inv,
    ):
        cap.apply_template_capability_config(42, tpl, actor_user_id=None)
    assert set_ov.call_count == 6
    knobs = {c.args[1] for c in set_ov.call_args_list}
    assert "dashboards.allowed_kinds" in knobs
    assert "ui.allowed_nav" in knobs
    assert "dashboards.write_membership_roles" in knobs
    inv.assert_called_once_with(42)


def test_tool_domain_allowed_respects_override() -> None:
    tenant_cap.register_tenant_capability_dependencies(
        _FakeCapabilityDeps({"tools.allowed_domains": frozenset({"rag", "knowledge"})})
    )
    try:
        assert tenant_cap.tool_domain_allowed_for_tenant(1, "rag") is True
        assert tenant_cap.tool_domain_allowed_for_tenant(1, "shared") is True
        assert tenant_cap.tool_domain_allowed_for_tenant(1, "workspace") is False
    finally:
        tenant_cap.register_tenant_capability_dependencies(_FakeCapabilityDeps())


def test_dashboard_kinds_from_override() -> None:
    tenant_cap.register_tenant_capability_dependencies(
        _FakeCapabilityDeps({"dashboards.allowed_kinds": frozenset({"projects", "ideas"})})
    )
    try:
        assert tenant_cap.dashboard_kind_allowed_for_tenant(1, "projects") is True
        assert tenant_cap.dashboard_kind_allowed_for_tenant(1, "pets") is False
    finally:
        tenant_cap.register_tenant_capability_dependencies(_FakeCapabilityDeps())


def test_nav_items_from_override() -> None:
    tenant_cap.register_tenant_capability_dependencies(
        _FakeCapabilityDeps({"ui.allowed_nav": frozenset({"home", "chat", "dashboard"})})
    )
    try:
        allowed = tenant_cap.tenant_allowed_nav_items(1)
        assert allowed is not None
        assert "chat" in allowed
        assert "studio" not in allowed
    finally:
        tenant_cap.register_tenant_capability_dependencies(_FakeCapabilityDeps())


def test_structure_edit_respects_write_membership_roles() -> None:
    tenant_cap.register_tenant_capability_dependencies(
        _FakeCapabilityDeps(
            {"dashboards.write_membership_roles": frozenset({"tenant_admin", "tenant_owner"})}
        )
    )
    try:
        assert tenant_cap.tenant_can_structure_edit_dashboards(1, "tenant_admin") is True
        assert tenant_cap.tenant_can_structure_edit_dashboards(1, "tenant_member") is False
    finally:
        tenant_cap.register_tenant_capability_dependencies(_FakeCapabilityDeps())
