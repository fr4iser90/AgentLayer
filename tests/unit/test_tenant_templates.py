"""Tenant templates and provisioning (Task 07)."""

from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from apps.backend.application.tenant_provisioning.use_cases import tenant_provision_service as provision
from apps.backend.application.tenant_provisioning.use_cases.tenant_template_loader import (
    get_template,
    list_templates_public,
    load_all_templates,
)


def test_load_seed_templates() -> None:
    templates = load_all_templates(reload=True)
    assert "tpl_default_ops" in templates
    assert "tpl_healthcare_ops" in templates
    assert templates["tpl_healthcare_ops"].vertical_profile == "healthcare_ops"


def test_list_templates_public_shape() -> None:
    items = list_templates_public()
    ids = {i["id"] for i in items}
    assert "tpl_default_ops" in ids
    assert all("vertical_profile" in i for i in items)


def test_unknown_template_raises() -> None:
    with pytest.raises(HTTPException) as exc:
        get_template("tpl_does_not_exist")
    assert exc.value.status_code == 400


def test_provision_applies_template_config() -> None:
    tenant_row = {"id": 99, "name": "Pilot Nord"}
    updated = {**tenant_row, "vertical_profile": "healthcare_ops"}
    tpl = get_template("tpl_healthcare_ops")
    with (
        patch.object(provision.db, "tenant_insert", return_value=tenant_row),
        patch.object(provision.db, "tenant_update_org_profile", return_value=updated) as upd,
        patch.object(provision, "apply_template_profession_config") as apply_cfg,
        patch.object(provision, "apply_template_capability_config") as apply_cap,
        patch.object(provision.db, "tenant_get", return_value=updated),
    ):
        out = provision.provision_tenant(name="Pilot Nord", template_id="tpl_healthcare_ops")
    upd.assert_called_once()
    apply_cfg.assert_called_once_with(99, tpl)
    apply_cap.assert_called_once()
    assert out["template_id"] == "tpl_healthcare_ops"
    assert out["tenant"]["vertical_profile"] == "healthcare_ops"


def test_provision_without_template_legacy() -> None:
    tenant_row = {"id": 2, "name": "Legacy"}
    with (
        patch.object(provision.db, "tenant_insert", return_value=tenant_row),
        patch.object(provision, "apply_template_profession_config") as apply_cfg,
        patch.object(provision.db, "tenant_get", return_value=tenant_row),
    ):
        out = provision.provision_tenant(name="Legacy")
    apply_cfg.assert_not_called()
    assert out["template_id"] is None


def test_seed_demo_requires_admin_user() -> None:
    tpl = get_template("tpl_default_ops")
    with (
        patch.object(provision.db, "tenant_insert", return_value={"id": 3, "name": "Demo"}),
        patch.object(provision.db, "tenant_update_org_profile"),
        patch.object(provision, "apply_template_profession_config"),
        patch.object(provision.db, "tenant_get", return_value={"id": 3}),
        patch.object(provision.db, "user_first_admin_id", return_value=None),
    ):
        with pytest.raises(ValueError, match="site admin"):
            provision.provision_tenant(
                name="Demo",
                template_id=tpl.id,
                seed_demo_content=True,
            )
