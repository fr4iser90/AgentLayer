"""P4 — dashboard feature access (global operator flag + per-user grant + quota).

Covers the pure policy (``domain/dashboards/access``) and the IO layer
(``infrastructure/dashboard/dashboard_access``) without a live DB: the ``db`` instance is
patched at its source (``apps.backend.infrastructure.db.db``), and the two scalar seams
(``global_dashboards_enabled`` / ``_load_user_dashboards_allowed``) are stubbed where convenient.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import patch

from apps.backend.domain.dashboards.access import (
    dashboards_feature_denied_message,
    dashboards_quota_reached_message,
    evaluate_dashboards_access,
)
from apps.backend.infrastructure.db import db
from apps.backend.infrastructure.dashboard import dashboard_access as mod


class _FakeCur:
    def __init__(self, value):
        self._value = value
        self.rowcount = value

    def execute(self, *args):
        pass

    def fetchone(self):
        return (self._value,)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class _FakeConn:
    def __init__(self, value):
        self._value = value

    def cursor(self):
        return _FakeCur(self._value)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class _FakePool:
    def __init__(self, value):
        self._value = value

    def connection(self):
        return _FakeConn(self._value)


def _fake_user(role, uid=None) -> SimpleNamespace:
    return SimpleNamespace(id=uid or uuid.uuid4(), role=role)


def _stub_db_pool(value) -> object:
    """Patch ``db.pool`` so ``db.pool().connection()`` yields our fake cursor."""
    return patch.object(db, "pool", lambda: _FakePool(value))


# --- pure policy (no IO) ---


def test_admin_and_site_admin_always_allowed() -> None:
    assert evaluate_dashboards_access(user_role="admin", dashboards_allowed=False) is True
    assert evaluate_dashboards_access(site_role="site_admin", dashboards_allowed=False) is True


def test_non_admin_follows_per_user_flag() -> None:
    assert evaluate_dashboards_access(user_role="user", dashboards_allowed=True) is True
    assert evaluate_dashboards_access(user_role="user", dashboards_allowed=False) is False


def test_denied_and_quota_messages_nonempty() -> None:
    assert dashboards_feature_denied_message()
    assert dashboards_quota_reached_message()


# --- user_may_use_dashboards composition ---


def test_global_flag_off_denies() -> None:
    with patch.object(mod, "global_dashboards_enabled", return_value=False):
        assert mod.user_may_use_dashboards(user=_fake_user("user")) is False


def test_admin_bypass_ignores_per_user_flag() -> None:
    with (
        patch.object(mod, "global_dashboards_enabled", return_value=True),
        patch.object(mod, "_load_user_dashboards_allowed", return_value=False),
        patch.object(db, "user_site_role", lambda _uid: None),
        patch.object(db, "user_role", lambda _uid: "admin"),
    ):
        assert mod.user_may_use_dashboards(user=_fake_user("admin")) is True


def test_site_admin_bypass_via_db() -> None:
    with (
        patch.object(mod, "global_dashboards_enabled", return_value=True),
        patch.object(mod, "_load_user_dashboards_allowed", return_value=False),
        patch.object(db, "user_site_role", lambda _uid: "site_admin"),
        patch.object(db, "user_role", lambda _uid: "user"),
    ):
        assert mod.user_may_use_dashboards(user_id=uuid.uuid4()) is True


def test_non_admin_grant_allows() -> None:
    with (
        patch.object(mod, "global_dashboards_enabled", return_value=True),
        patch.object(mod, "_load_user_dashboards_allowed", return_value=True),
        patch.object(db, "user_site_role", lambda _uid: "site_user"),
        patch.object(db, "user_role", lambda _uid: "user"),
    ):
        assert mod.user_may_use_dashboards(user_id=uuid.uuid4()) is True


def test_non_admin_grant_revoked_denies() -> None:
    with (
        patch.object(mod, "global_dashboards_enabled", return_value=True),
        patch.object(mod, "_load_user_dashboards_allowed", return_value=False),
        patch.object(db, "user_site_role", lambda _uid: "site_user"),
        patch.object(db, "user_role", lambda _uid: "user"),
    ):
        assert mod.user_may_use_dashboards(user_id=uuid.uuid4()) is False


# --- create gate: dashboards_feature_permission_error ---


def test_permission_error_access_denied() -> None:
    with patch.object(mod, "user_may_use_dashboards", return_value=False):
        err = mod.dashboards_feature_permission_error(user=_fake_user("user"))
    assert err == dashboards_feature_denied_message()


def test_permission_error_quota_reached() -> None:
    with patch.object(mod, "user_may_use_dashboards", return_value=True):
        err = mod.dashboards_feature_permission_error(user=_fake_user("user"), current_count=2, quota=2)
    assert err == dashboards_quota_reached_message()


def test_permission_error_ok_under_quota() -> None:
    with patch.object(mod, "user_may_use_dashboards", return_value=True):
        err = mod.dashboards_feature_permission_error(user=_fake_user("user"), current_count=0, quota=1)
    assert err is None


# --- quota reader ---


def test_quota_for_default_one_when_no_uid() -> None:
    with patch.object(mod, "_resolve_uid", return_value=None):
        assert mod.dashboards_quota_for(None) == 1


def test_quota_for_reads_value_from_db() -> None:
    uid = uuid.uuid4()
    with (
        patch.object(mod, "_resolve_uid", return_value=uid),
        _stub_db_pool(5),
    ):
        assert mod.dashboards_quota_for(uid) == 5


def test_quota_for_floors_at_one() -> None:
    uid = uuid.uuid4()
    with (
        patch.object(mod, "_resolve_uid", return_value=uid),
        _stub_db_pool(0),
    ):
        assert mod.dashboards_quota_for(uid) == 1


def test_quota_reader_names_the_real_column() -> None:
    """The quota column is ``users.dashboard_quota`` (singular).

    ``_FakeCur`` above discards the SQL it is handed, so every existing
    quota test passed while the reader queried ``dashboards_quota`` — a
    column that does not exist. Against a real database that raises
    UndefinedColumn, the broad ``except`` swallowed it, and every user was
    silently capped at one dashboard no matter what the admin API wrote.
    A stub that ignores the query cannot catch a wrong column, so this
    asserts the SQL text itself.
    """
    seen: list[str] = []

    class _RecordingCur(_FakeCur):
        def execute(self, *args):
            if args:
                seen.append(str(args[0]))
            return None

    class _RecordingConn:
        def cursor(self):
            return _RecordingCur(1)

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    class _RecordingPool:
        def connection(self):
            return _RecordingConn()

    uid = uuid.uuid4()
    with (
        patch.object(mod, "_resolve_uid", return_value=uid),
        patch.object(db, "pool", lambda: _RecordingPool()),
    ):
        mod.dashboards_quota_for(uid)

    assert seen, "quota reader issued no SQL"
    sql = " ".join(seen)
    assert "dashboard_quota" in sql, f"reader does not query dashboard_quota: {sql}"
    assert "dashboards_quota" not in sql, f"reader queries the non-existent plural column: {sql}"


# --- current_dashboards_count / delete_user_dashboards ---


def test_current_dashboards_count_reads_from_db() -> None:
    uid = uuid.uuid4()
    with (
        patch.object(mod, "_resolve_uid", return_value=uid),
        _stub_db_pool(3),
    ):
        assert mod.current_dashboards_count(uid, 7) == 3


def test_current_dashboards_count_zero_when_no_uid() -> None:
    assert mod.current_dashboards_count(None, 7) == 0


def test_delete_user_dashboards_returns_rowcount() -> None:
    uid = uuid.uuid4()
    with (
        patch.object(mod, "_resolve_uid", return_value=uid),
        _stub_db_pool(2),
    ):
        assert mod.delete_user_dashboards(uid) == 2


def test_delete_user_dashboards_zero_when_no_uid() -> None:
    assert mod.delete_user_dashboards(None) == 0
