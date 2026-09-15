"""P6 (Weg B): per-user admin capabilities + the site-admin boundary.

Covers the pure capability policy, the ``require_admin_capability`` guard, and the
security-critical rule that a delegated ``user.manage`` holder may edit any
non-site-admin user but never a site admin (nor create one).
"""

from __future__ import annotations

import asyncio
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from apps.backend.domain.access import capabilities as cap_mod
from apps.backend.infrastructure.identity import auth as auth_mod
from apps.backend.api.platform.controllers import admin_users_api as users_mod


def _user(uid: object = "user") -> MagicMock:
    return MagicMock(id=uid)


# --- pure policy ---


def test_evaluate_access_site_admin_holds_everything() -> None:
    assert cap_mod.evaluate_access(site_role="site_admin", capabilities=[], capability="agent.assign") is True
    assert cap_mod.evaluate_access(site_role="Site_Admin", capabilities=None, capability="user.manage") is True


def test_evaluate_access_delegated_needs_granted_capability() -> None:
    ev = cap_mod.evaluate_access
    assert ev(site_role="site_user", capabilities=["agent.assign"], capability="agent.assign") is True
    assert ev(site_role="site_user", capabilities=["user.manage"], capability="agent.assign") is False
    assert ev(site_role="site_user", capabilities=None, capability="agent.assign") is False
    # case/space-insensitive slug matching
    assert ev(site_role="site_user", capabilities=["  Agent.Assign "], capability="agent.assign") is True


# --- guard ---


def test_guard_accepts_site_admin_without_any_capability() -> None:
    user = _user()

    async def run() -> None:
        with (
            patch.object(auth_mod, "get_current_user", new=AsyncMock(return_value=user)),
            patch.object(auth_mod.db, "user_site_role", return_value="site_admin"),
            patch.object(auth_mod.db, "user_capabilities", return_value=[]),
        ):
            out = await auth_mod.require_admin_capability(MagicMock(), "agent.assign")
        assert out is user

    asyncio.run(run())


def test_guard_accepts_delegated_with_granted_capability() -> None:
    user = _user()

    async def run() -> None:
        with (
            patch.object(auth_mod, "get_current_user", new=AsyncMock(return_value=user)),
            patch.object(auth_mod.db, "user_site_role", return_value="site_user"),
            patch.object(auth_mod.db, "user_capabilities", return_value=["user.manage"]),
        ):
            out = await auth_mod.require_admin_capability(MagicMock(), "user.manage")
        assert out is user

    asyncio.run(run())


def test_guard_rejects_delegated_without_capability() -> None:
    user = _user()

    async def run() -> None:
        with (
            patch.object(auth_mod, "get_current_user", new=AsyncMock(return_value=user)),
            patch.object(auth_mod.db, "user_site_role", return_value="site_user"),
            patch.object(auth_mod.db, "user_capabilities", return_value=[]),
        ):
            with pytest.raises(HTTPException) as exc:
                await auth_mod.require_admin_capability(MagicMock(), "user.manage")
        assert exc.value.status_code == 403

    asyncio.run(run())


def test_guard_rejects_unknown_capability_slug() -> None:
    user = _user()

    async def run() -> None:
        with patch.object(auth_mod, "get_current_user", new=AsyncMock(return_value=user)):
            with pytest.raises(HTTPException) as exc:
                await auth_mod.require_admin_capability(MagicMock(), "bogus.cap")
        assert exc.value.status_code == 403

    asyncio.run(run())


# --- admin_patch_user boundary ---

_TARGET_SITE_ADMIN = uuid.UUID("11111111-1111-1111-1111-111111111111")
_TARGET_PLAIN = uuid.UUID("22222222-2222-2222-2222-222222222222")


def test_patch_delegated_cannot_touch_site_admin() -> None:
    delegated = _user("delegated")
    target = _user("siteadmin")

    async def run() -> None:
        with (
            patch.object(users_mod, "require_admin_capability", new=AsyncMock(return_value=delegated)),
            patch.object(users_mod, "get_user_by_id", return_value=target),
            patch.object(
                users_mod.db,
                "user_site_role",
                side_effect=lambda uid: "site_admin" if str(uid) == "siteadmin" else "site_user",
            ),
        ):
            # 403 is raised before any DB write, so db.query need not be patched
            with pytest.raises(HTTPException) as exc:
                await users_mod.admin_patch_user(
                    MagicMock(),
                    _TARGET_SITE_ADMIN,
                    users_mod.AdminPatchUserBody(schedules_allowed=True),
                )
        assert exc.value.status_code == 403

    asyncio.run(run())


def test_patch_delegated_can_edit_regular_user() -> None:
    delegated = _user("delegated")
    target = _user("plain")
    writes: list[tuple[str, tuple]] = []

    async def run() -> None:
        def _query(sql: str, params: tuple) -> None:
            writes.append((sql, params))

        with (
            patch.object(users_mod, "require_admin_capability", new=AsyncMock(return_value=delegated)),
            patch.object(users_mod, "get_user_by_id", return_value=target),
            patch.object(users_mod.db, "user_site_role", return_value="site_user"),
            patch.object(users_mod.db, "query", side_effect=_query),
            patch.object(users_mod.db, "user_tenant_id", return_value=1),
        ):
            out = await users_mod.admin_patch_user(
                MagicMock(),
                _TARGET_PLAIN,
                users_mod.AdminPatchUserBody(schedules_allowed=True),
            )
        assert out["ok"] is True
        assert any("schedules_allowed" in sql for sql, _ in writes)

    asyncio.run(run())


def test_patch_rejects_unknown_capability_slug() -> None:
    delegated = _user("delegated")
    target = _user("plain")

    async def run() -> None:
        with (
            patch.object(users_mod, "require_admin_capability", new=AsyncMock(return_value=delegated)),
            patch.object(users_mod, "get_user_by_id", return_value=target),
            patch.object(users_mod.db, "user_site_role", return_value="site_user"),
            patch.object(users_mod.db, "query", new=MagicMock()),
            patch.object(users_mod.db, "user_tenant_id", return_value=1),
        ):
            with pytest.raises(HTTPException) as exc:
                await users_mod.admin_patch_user(
                    MagicMock(),
                    _TARGET_PLAIN,
                    users_mod.AdminPatchUserBody(capabilities=["bogus.cap"]),
                )
        assert exc.value.status_code == 400

    asyncio.run(run())


def test_patch_writes_normalized_capabilities() -> None:
    delegated = _user("delegated")
    target = _user("plain")
    captured: dict[str, object] = {}

    async def run() -> None:
        def _query(sql: str, params: tuple) -> None:
            captured["sql"] = sql
            captured["params"] = params

        with (
            patch.object(users_mod, "require_admin_capability", new=AsyncMock(return_value=delegated)),
            patch.object(users_mod, "get_user_by_id", return_value=target),
            patch.object(users_mod.db, "user_site_role", return_value="site_user"),
            patch.object(users_mod.db, "query", side_effect=_query),
            patch.object(users_mod.db, "user_tenant_id", return_value=1),
        ):
            out = await users_mod.admin_patch_user(
                MagicMock(),
                _TARGET_PLAIN,
                users_mod.AdminPatchUserBody(capabilities=["User.Manage", "  agent.assign ", "user.manage"]),
            )
        assert out["ok"] is True
        assert captured["params"][0].obj == ["agent.assign", "user.manage"]
        assert "capabilities" in str(captured["sql"])

    asyncio.run(run())


# --- admin_create_user boundary ---


def test_create_delegated_cannot_make_site_admin() -> None:
    delegated = _user("delegated")

    async def run() -> None:
        with (
            patch.object(users_mod, "require_admin_capability", new=AsyncMock(return_value=delegated)),
            patch.object(users_mod.db, "user_site_role", return_value="site_user"),
        ):
            with pytest.raises(HTTPException) as exc:
                await users_mod.admin_create_user(
                    MagicMock(),
                    users_mod.AdminCreateUserBody(
                        email="a@b.c", password="secretsecret", role="admin", tenant_id=1
                    ),
                )
        assert exc.value.status_code == 403

    asyncio.run(run())


def test_create_delegated_can_make_regular_user() -> None:
    delegated = _user("delegated")
    created = SimpleNamespace(id=uuid.uuid4(), role="user", email="a@b.c")

    async def run() -> None:
        with (
            patch.object(users_mod, "require_admin_capability", new=AsyncMock(return_value=delegated)),
            patch.object(users_mod.db, "user_site_role", return_value="site_user"),
            patch.object(users_mod.db, "tenant_exists", return_value=True),
            patch.object(users_mod, "get_user_by_email", return_value=None),
            patch.object(users_mod, "create_user", return_value=created),
        ):
            out = await users_mod.admin_create_user(
                MagicMock(),
                users_mod.AdminCreateUserBody(
                    email="a@b.c", password="secretsecret", role="user", tenant_id=1
                ),
            )
        assert out["ok"] is True
        assert out["role"] == "user"

    asyncio.run(run())
