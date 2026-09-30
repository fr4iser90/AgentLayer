"""Smoke tests for ``plugins/tools/platform/operator/admin.py``."""

from __future__ import annotations

import json
import uuid
from unittest.mock import patch

import pytest

from apps.backend.domain.plugin_system.registry import reload_registry
from apps.backend.infrastructure.identity import console_access as console_guard


@pytest.fixture
def admin_uid() -> uuid.UUID:
    return uuid.uuid4()


def test_operator_settings_get_requires_site_admin(admin_uid: uuid.UUID) -> None:
    from plugins.tools.platform.operator import admin as oa

    # The console reads the call's identity through the shared in-process guard.
    with patch.object(console_guard, "get_identity", return_value=(1, admin_uid)):
        with patch.object(oa.db, "user_site_role", return_value="site_user"):
            out = json.loads(oa.settings_get({}))
    assert out["ok"] is False
    assert "site admin required" == out["error"]


def test_operator_settings_get_ok_when_site_admin(admin_uid: uuid.UUID) -> None:
    from plugins.tools.platform.operator import admin as oa

    fake_settings = {"discord_bot_enabled": False}
    fake_if = {"agent_mode": "sandbox"}

    with patch.object(console_guard, "get_identity", return_value=(1, admin_uid)):
        with patch.object(oa.db, "user_site_role", return_value="site_admin"):
            with patch.object(oa, "operator_settings_public_dict", return_value=fake_settings):
                with patch.object(oa, "interface_hints_public", return_value=fake_if):
                    out = json.loads(oa.settings_get({}))
    assert out["ok"] is True
    assert out["settings"] == fake_settings
    assert out["interfaces"] == fake_if


def test_operator_admin_tools_registered() -> None:
    reg = reload_registry(scope="all")
    for name in (
        "settings_get",
        "tenants_list",
        "reload_tools",
    ):
        assert name in reg._handlers, name
