"""Tenant template capability allowlists."""

from __future__ import annotations

from unittest.mock import patch

from apps.backend.application.tenant_provisioning.use_cases import tenant_capability_policy as cap
from apps.backend.application.tenant_provisioning.use_cases.tenant_template_loader import get_template
from apps.backend.domain.tenant_capability import policy as tenant_cap
from apps.backend.domain.tenant_templates.entities import TenantTemplate


class _FakeCapabilityDeps:
    def __init__(self, values: dict[str, frozenset[str]]) -> None:
        self._values = values

    def config_string_list(self, tenant_id: int, knob_id: str) -> frozenset[str] | None:
        return self._values.get(knob_id)


def test_healthcare_template_has_capability_fields() -> None:
    tpl = get_template("tpl_healthcare_ops")
    assert "knowledge_companion" in tpl.enabled_agent_ids
    assert "rag" in tpl.enabled_tool_domains


def test_apply_template_capability_config_writes_overrides() -> None:
    tpl = TenantTemplate(
        id="t",
        name="T",
        description="",
        vertical_profile="healthcare_ops",
        departments=(),
        profession_roles=(),
        workflow_defaults={},
        seed_content_glob=None,
        enabled_agent_ids=("general", "knowledge_companion"),
        enabled_tool_domains=("rag", "shared"),
    )
    with (
        patch.object(cap, "set_override") as set_ov,
        patch.object(cap, "invalidate_agent_config_cache") as inv,
    ):
        cap.apply_template_capability_config(42, tpl, actor_user_id=None)
    assert set_ov.call_count == 3
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
        tenant_cap.register_tenant_capability_dependencies(_FakeCapabilityDeps({}))
