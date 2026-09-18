"""P6 (Weg B): per-user admin capabilities, the site-admin boundary, and tenant scope.

Covers the pure capability policy, the ``require_admin_capability`` /
``require_admin_scope`` guards, and the two rules that matter:

* a delegated holder may never touch a site admin, and
* a delegated holder may never reach outside their own tenant — the latter was
  absent before the scope layer and let a company admin list, create and move
  users of another company.
"""

from __future__ import annotations

import asyncio
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from apps.backend.domain.access import capabilities as cap_mod
from apps.backend.domain.access.capabilities import AdminScope, AdminScopeError
from apps.backend.infrastructure.identity import auth as auth_mod
from apps.backend.api.platform.controllers import admin_users_api as users_mod


def _user(uid: object = "user") -> MagicMock:
    return MagicMock(id=uid)


def _scope(*, site_wide: bool = False, tenant_ids=(1,)) -> AdminScope:
    return AdminScope(
        actor_id=uuid.uuid4(),
        site_wide=site_wide,
        tenant_ids=frozenset(tenant_ids),
    )


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


# --- AdminScope value object ---


def test_scope_site_wide_allows_any_tenant() -> None:
    s = _scope(site_wide=True, tenant_ids=())
    assert s.allows_tenant(99) is True
    assert s.tenant_filter() is None  # None = do not filter


def test_scope_delegated_denies_other_tenants() -> None:
    s = _scope(tenant_ids=(1,))
    assert s.allows_tenant(1) is True
    assert s.allows_tenant(2) is False
    assert s.allows_tenant(None) is False
    assert s.tenant_filter() == frozenset({1})


def test_scope_require_tenant_returns_in_scope() -> None:
    assert _scope(tenant_ids=(1, 3)).require_tenant(3) == 3


def test_scope_require_tenant_rejects_out_of_scope() -> None:
    with pytest.raises(AdminScopeError):
        _scope(tenant_ids=(1,)).require_tenant(2)


def test_scope_require_site_wide_blocks_delegated() -> None:
    with pytest.raises(AdminScopeError):
        _scope(site_wide=False).require_site_wide("moving a user")
    _scope(site_wide=True).require_site_wide("moving a user")


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


def test_guard_scope_site_admin_is_site_wide() -> None:
    user = _user()

    async def run() -> None:
        with (
            patch.object(auth_mod, "get_current_user", new=AsyncMock(return_value=user)),
            patch.object(auth_mod.db, "user_site_role", return_value="site_admin"),
            patch.object(auth_mod.db, "user_capabilities", return_value=[]),
            patch.object(auth_mod.db, "user_tenant_id", return_value=1),
        ):
            scope = await auth_mod.require_admin_scope(MagicMock(), "user.manage")
        assert scope.site_wide is True
        assert scope.tenant_filter() is None

    asyncio.run(run())


def test_guard_scope_delegated_is_confined_to_own_tenant() -> None:
    user = _user()

    async def run() -> None:
        with (
            patch.object(auth_mod, "get_current_user", new=AsyncMock(return_value=user)),
            patch.object(auth_mod.db, "user_site_role", return_value="site_user"),
            patch.object(auth_mod.db, "user_capabilities", return_value=["user.manage"]),
            patch.object(auth_mod.db, "user_tenant_id", return_value=7),
        ):
            scope = await auth_mod.require_admin_scope(MagicMock(), "user.manage")
        assert scope.site_wide is False
        assert scope.tenant_filter() == frozenset({7})
        assert scope.allows_tenant(8) is False

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
_TARGET_OTHER_TENANT = uuid.UUID("33333333-3333-3333-3333-333333333333")


def test_patch_delegated_cannot_touch_site_admin() -> None:
    target = _user("siteadmin")

    async def run() -> None:
        with (
            patch.object(users_mod, "require_admin_scope", new=AsyncMock(return_value=_scope())),
            patch.object(users_mod, "get_user_by_id", return_value=target),
            patch.object(
                users_mod.db,
                "user_site_role",
                side_effect=lambda uid: "site_admin" if str(uid) == "siteadmin" else "site_user",
            ),
            patch.object(users_mod.db, "user_tenant_id", return_value=1),
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
    target = _user("plain")
    writes: list[tuple[str, tuple]] = []

    async def run() -> None:
        def _query(sql: str, params: tuple) -> None:
            writes.append((sql, params))

        with (
            patch.object(users_mod, "require_admin_scope", new=AsyncMock(return_value=_scope(tenant_ids=(1,)))),
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


def test_patch_delegated_cannot_edit_user_of_another_tenant() -> None:
    """The hole this closes: tenant-1 admin editing a tenant-2 user."""
    target = _user("other")

    async def run() -> None:
        with (
            patch.object(users_mod, "require_admin_scope", new=AsyncMock(return_value=_scope(tenant_ids=(1,)))),
            patch.object(users_mod, "get_user_by_id", return_value=target),
            patch.object(users_mod.db, "user_site_role", return_value="site_user"),
            patch.object(users_mod.db, "query", new=MagicMock()),
            patch.object(users_mod.db, "user_tenant_id", return_value=2),
        ):
            with pytest.raises(HTTPException) as exc:
                await users_mod.admin_patch_user(
                    MagicMock(),
                    _TARGET_OTHER_TENANT,
                    users_mod.AdminPatchUserBody(schedules_allowed=True),
                )
        assert exc.value.status_code == 403

    asyncio.run(run())


def test_patch_delegated_cannot_move_user_between_tenants() -> None:
    moved: list[tuple] = []

    async def run() -> None:
        with (
            patch.object(users_mod, "require_admin_scope", new=AsyncMock(return_value=_scope(tenant_ids=(1,)))),
            patch.object(users_mod, "get_user_by_id", return_value=_user("plain")),
            patch.object(users_mod.db, "user_site_role", return_value="site_user"),
            patch.object(users_mod.db, "user_tenant_id", return_value=1),
            patch.object(users_mod.db, "tenant_exists", return_value=True),
            patch.object(users_mod.db, "query", new=MagicMock()),
            patch.object(
                users_mod,
                "update_user_tenant",
                side_effect=lambda uid, tid: moved.append((uid, tid)) or True,
            ),
        ):
            with pytest.raises(HTTPException) as exc:
                await users_mod.admin_patch_user(
                    MagicMock(),
                    _TARGET_PLAIN,
                    users_mod.AdminPatchUserBody(tenant_id=2),
                )
        assert exc.value.status_code == 403
        assert moved == []

    asyncio.run(run())


def test_patch_delegated_may_echo_own_tenant_unchanged() -> None:
    """The admin UI posts the row back with tenant_id set; same-value must not 403."""
    moved: list[tuple] = []

    async def run() -> None:
        with (
            patch.object(users_mod, "require_admin_scope", new=AsyncMock(return_value=_scope(tenant_ids=(1,)))),
            patch.object(users_mod, "get_user_by_id", return_value=_user("plain")),
            patch.object(users_mod.db, "user_site_role", return_value="site_user"),
            patch.object(users_mod.db, "user_tenant_id", return_value=1),
            patch.object(users_mod.db, "query", new=MagicMock()),
            patch.object(
                users_mod,
                "update_user_tenant",
                side_effect=lambda uid, tid: moved.append((uid, tid)) or True,
            ),
        ):
            out = await users_mod.admin_patch_user(
                MagicMock(),
                _TARGET_PLAIN,
                users_mod.AdminPatchUserBody(tenant_id=1, schedules_allowed=True),
            )
        assert out["ok"] is True
        assert moved == []  # unchanged tenant is not a move

    asyncio.run(run())


def test_patch_site_admin_can_move_user_between_tenants() -> None:
    moved: list[tuple] = []

    async def run() -> None:
        with (
            patch.object(users_mod, "require_admin_scope", new=AsyncMock(return_value=_scope(site_wide=True))),
            patch.object(users_mod, "get_user_by_id", return_value=_user("plain")),
            patch.object(users_mod.db, "user_site_role", return_value="site_user"),
            patch.object(users_mod.db, "user_tenant_id", return_value=1),
            patch.object(users_mod.db, "tenant_exists", return_value=True),
            patch.object(users_mod.db, "query", new=MagicMock()),
            patch.object(
                users_mod,
                "update_user_tenant",
                side_effect=lambda uid, tid: moved.append((uid, tid)) or True,
            ),
        ):
            out = await users_mod.admin_patch_user(
                MagicMock(),
                _TARGET_PLAIN,
                users_mod.AdminPatchUserBody(tenant_id=2),
            )
        assert out["ok"] is True
        assert moved == [(_TARGET_PLAIN, 2)]

    asyncio.run(run())


def test_patch_rejects_unknown_capability_slug() -> None:
    async def run() -> None:
        with (
            patch.object(users_mod, "require_admin_scope", new=AsyncMock(return_value=_scope(tenant_ids=(1,)))),
            patch.object(users_mod, "get_user_by_id", return_value=_user("plain")),
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
    captured: dict[str, object] = {}

    async def run() -> None:
        def _query(sql: str, params: tuple) -> None:
            captured["sql"] = sql
            captured["params"] = params

        with (
            patch.object(users_mod, "require_admin_scope", new=AsyncMock(return_value=_scope(tenant_ids=(1,)))),
            patch.object(users_mod, "get_user_by_id", return_value=_user("plain")),
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


# --- admin_list_users scope ---


def test_list_users_delegated_passes_own_tenant_filter() -> None:
    captured: dict[str, object] = {}

    async def run() -> None:
        with (
            patch.object(users_mod, "require_admin_scope", new=AsyncMock(return_value=_scope(tenant_ids=(4,)))),
            patch.object(
                users_mod,
                "list_all_users",
                side_effect=lambda tenant_ids=None: captured.update(tenant_ids=tenant_ids) or [],
            ),
        ):
            out = await users_mod.admin_list_users(MagicMock())
        assert out == {"users": []}
        assert captured["tenant_ids"] == frozenset({4})

    asyncio.run(run())


def test_list_users_site_admin_passes_no_filter() -> None:
    captured: dict[str, object] = {}

    async def run() -> None:
        with (
            patch.object(users_mod, "require_admin_scope", new=AsyncMock(return_value=_scope(site_wide=True))),
            patch.object(
                users_mod,
                "list_all_users",
                side_effect=lambda tenant_ids=None: captured.update(tenant_ids=tenant_ids) or [],
            ),
        ):
            await users_mod.admin_list_users(MagicMock())
        assert captured["tenant_ids"] is None

    asyncio.run(run())


# --- admin_create_user boundary ---


def test_create_delegated_cannot_make_site_admin() -> None:
    async def run() -> None:
        with (
            patch.object(users_mod, "require_admin_scope", new=AsyncMock(return_value=_scope(tenant_ids=(1,)))),
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


def test_create_delegated_can_make_regular_user_in_own_tenant() -> None:
    created = SimpleNamespace(id=uuid.uuid4(), role="user", email="a@b.c")

    async def run() -> None:
        with (
            patch.object(users_mod, "require_admin_scope", new=AsyncMock(return_value=_scope(tenant_ids=(1,)))),
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


def test_create_delegated_cannot_make_user_in_another_tenant() -> None:
    """Tenant-1 admin creating into tenant 2 — the second half of the hole."""
    created_calls: list[tuple] = []

    async def run() -> None:
        with (
            patch.object(users_mod, "require_admin_scope", new=AsyncMock(return_value=_scope(tenant_ids=(1,)))),
            patch.object(users_mod.db, "tenant_exists", return_value=True),
            patch.object(users_mod, "get_user_by_email", return_value=None),
            patch.object(
                users_mod, "create_user", side_effect=lambda *a, **kw: created_calls.append(a)
            ),
        ):
            with pytest.raises(HTTPException) as exc:
                await users_mod.admin_create_user(
                    MagicMock(),
                    users_mod.AdminCreateUserBody(
                        email="x@corp-b.example", password="secretsecret", role="user", tenant_id=2
                    ),
                )
        assert exc.value.status_code == 403
        assert created_calls == []

    asyncio.run(run())
