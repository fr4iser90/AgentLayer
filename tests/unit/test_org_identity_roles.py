"""Task 03b — deployment mode, site/tenant role guards."""

from __future__ import annotations

import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from apps.backend.application.identity.use_cases.request_auth import agent_effective_role
from apps.backend.domain.setup import instance as setup_mod
from apps.backend.infrastructure.identity import auth as auth_mod


def test_apply_setup_deployment_mode_rejects_invalid() -> None:
    with patch.object(setup_mod, "is_first_start", return_value=True):
        with pytest.raises(HTTPException) as exc:
            setup_mod.apply_setup_deployment_mode(deployment_mode="invalid")
    assert exc.value.status_code == 400


def test_apply_setup_deployment_mode_rejects_after_admin() -> None:
    with patch.object(setup_mod, "is_first_start", return_value=False):
        with pytest.raises(HTTPException) as exc:
            setup_mod.apply_setup_deployment_mode(deployment_mode="agent_system")
    assert exc.value.status_code == 409


def test_apply_setup_deployment_mode_persists_mode() -> None:
    with (
        patch.object(setup_mod, "is_first_start", return_value=True),
        patch.object(setup_mod, "apply_deployment_mode_patch") as patch_fn,
    ):
        out = setup_mod.apply_setup_deployment_mode(deployment_mode="multi_tenant")
    assert out == {"ok": True, "deployment_mode": "multi_tenant"}
    patch_fn.assert_called_once_with("multi_tenant")


def test_require_site_admin_rejects_site_user() -> None:
    user = MagicMock(id=uuid.uuid4())
    request = MagicMock()

    async def run() -> None:
        with (
            patch.object(auth_mod, "get_current_user", new=AsyncMock(return_value=user)),
            patch.object(auth_mod.db, "user_site_role", return_value="site_user"),
        ):
            with pytest.raises(HTTPException) as exc:
                await auth_mod.require_site_admin(request)
            assert exc.value.status_code == 403

    asyncio.run(run())


def test_require_tenant_admin_unavailable_in_agent_system() -> None:
    user = MagicMock(id=uuid.uuid4())
    request = MagicMock()

    async def run() -> None:
        with (
            patch.object(auth_mod, "get_current_user", new=AsyncMock(return_value=user)),
            patch(
                "apps.backend.infrastructure.settings.operator_settings.has_org_surface",
                return_value=False,
            ),
        ):
            with pytest.raises(HTTPException) as exc:
                await auth_mod.require_tenant_admin(request)
            assert exc.value.status_code == 404

    asyncio.run(run())


def test_require_tenant_admin_rejects_member() -> None:
    user = MagicMock(id=uuid.uuid4())
    request = MagicMock()

    async def run() -> None:
        with (
            patch.object(auth_mod, "get_current_user", new=AsyncMock(return_value=user)),
            patch(
                "apps.backend.infrastructure.settings.operator_settings.has_org_surface",
                return_value=True,
            ),
            patch.object(auth_mod.db, "user_tenant_id", return_value=1),
            patch.object(auth_mod.db, "user_is_tenant_admin", return_value=False),
        ):
            with pytest.raises(HTTPException) as exc:
                await auth_mod.require_tenant_admin(request)
            assert exc.value.status_code == 403

    asyncio.run(run())


def test_require_tenant_admin_accepts_owner() -> None:
    user = MagicMock(id=uuid.uuid4())
    request = MagicMock()

    async def run() -> None:
        with (
            patch.object(auth_mod, "get_current_user", new=AsyncMock(return_value=user)),
            patch(
                "apps.backend.infrastructure.settings.operator_settings.has_org_surface",
                return_value=True,
            ),
            patch.object(auth_mod.db, "user_tenant_id", return_value=1),
            patch.object(auth_mod.db, "user_is_tenant_admin", return_value=True),
        ):
            out = await auth_mod.require_tenant_admin(request)
            assert out is user

    asyncio.run(run())


def test_agent_effective_role_ignores_legacy_admin_when_site_user() -> None:
    """The P1 escalation class: role='admin' + site_role='site_user' must not elevate."""
    uid = uuid.uuid4()
    with patch.object(auth_mod.db, "user_site_admin", return_value=False):
        assert agent_effective_role(uid, "admin") == "user"


def test_agent_effective_role_follows_site_admin() -> None:
    uid = uuid.uuid4()
    with patch.object(auth_mod.db, "user_site_admin", return_value=True):
        assert agent_effective_role(uid, "user") == "admin"


def test_agent_effective_role_falls_back_when_lookup_fails() -> None:
    uid = uuid.uuid4()
    with patch.object(auth_mod.db, "user_site_admin", side_effect=RuntimeError("db down")):
        assert agent_effective_role(uid, "admin") == "admin"
        assert agent_effective_role(uid, None) == "user"


def test_agent_effective_role_without_user_id_uses_fallback() -> None:
    assert agent_effective_role(None, "admin") == "admin"
    assert agent_effective_role(None, None) == "user"
