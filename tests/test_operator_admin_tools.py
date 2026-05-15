"""Smoke tests for ``plugins/tools/capabilities/platform/operator_admin.py``."""

from __future__ import annotations

import json
import uuid
from unittest.mock import patch

import pytest

from apps.backend.domain.plugin_system.registry import reload_registry


@pytest.fixture
def admin_uid() -> uuid.UUID:
    return uuid.uuid4()


def test_operator_settings_get_requires_admin_identity(admin_uid: uuid.UUID) -> None:
    from plugins.tools.capabilities.platform import operator_admin as oa

    with patch.object(oa, "get_identity", return_value=(1, admin_uid)):
        with patch.object(oa.db, "user_role", return_value="user"):
            out = json.loads(oa.operator_settings_get({}))
    assert out["ok"] is False
    assert "admin" in out["error"].lower()


def test_operator_settings_get_ok_when_admin(admin_uid: uuid.UUID) -> None:
    from plugins.tools.capabilities.platform import operator_admin as oa

    fake_settings = {"discord_bot_enabled": False}
    fake_if = {"agent_mode": "sandbox"}

    with patch.object(oa, "get_identity", return_value=(1, admin_uid)):
        with patch.object(oa.db, "user_role", return_value="admin"):
            with patch.object(oa, "operator_settings_public_dict", return_value=fake_settings):
                with patch.object(oa, "interface_hints_public", return_value=fake_if):
                    out = json.loads(oa.operator_settings_get({}))
    assert out["ok"] is True
    assert out["settings"] == fake_settings
    assert out["interfaces"] == fake_if


def test_operator_admin_tools_registered() -> None:
    reg = reload_registry(scope="all")
    for name in (
        "operator_settings_get",
        "admin_tenants_list",
        "admin_reload_tools",
    ):
        assert name in reg._handlers, name
