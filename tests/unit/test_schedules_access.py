"""Tests for schedules feature access (admin-only default + per-user grant)."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

from apps.backend.domain.scheduling.access import (
    evaluate_schedules_access,
    schedule_feature_permission_error_from_flags,
)
from apps.backend.domain.scheduling.targets import schedule_permission_error
from apps.backend.infrastructure.scheduling import schedules_access as infra


def test_evaluate_admin_and_grant() -> None:
    assert evaluate_schedules_access(user_role="admin") is True
    assert evaluate_schedules_access(user_role="user", schedules_allowed=False) is False
    assert evaluate_schedules_access(user_role="user", schedules_allowed=True) is True
    assert evaluate_schedules_access(user_role="user", site_role="site_admin") is True
    assert schedule_feature_permission_error_from_flags(user_role="user") is not None
    assert schedule_feature_permission_error_from_flags(user_role="admin") is None


def test_infra_user_without_grant_denied() -> None:
    uid = uuid.uuid4()

    class _Cur:
        def execute(self, *_a, **_k):
            return None

        def fetchone(self):
            return (False,)

        def __enter__(self):
            return self

        def __exit__(self, *_a):
            return False

    class _Conn:
        def cursor(self):
            return _Cur()

        def __enter__(self):
            return self

        def __exit__(self, *_a):
            return False

    pool = MagicMock()
    pool.connection.return_value = _Conn()

    with (
        patch("apps.backend.infrastructure.db.db.user_role", return_value="user"),
        patch("apps.backend.infrastructure.db.db.user_site_role", return_value=None),
        patch("apps.backend.infrastructure.db.db.pool", return_value=pool),
    ):
        assert infra.user_may_use_schedules(user_id=uid, user_role="user") is False
        err = infra.schedule_feature_permission_error(user_id=uid, user_role="user")
        assert err is not None
        assert "schedules_allowed" in err


def test_infra_user_with_grant_allowed() -> None:
    uid = uuid.uuid4()

    class _Cur:
        def execute(self, *_a, **_k):
            return None

        def fetchone(self):
            return (True,)

        def __enter__(self):
            return self

        def __exit__(self, *_a):
            return False

    class _Conn:
        def cursor(self):
            return _Cur()

        def __enter__(self):
            return self

        def __exit__(self, *_a):
            return False

    pool = MagicMock()
    pool.connection.return_value = _Conn()

    with (
        patch("apps.backend.infrastructure.db.db.user_role", return_value="user"),
        patch("apps.backend.infrastructure.db.db.user_site_role", return_value=None),
        patch("apps.backend.infrastructure.db.db.pool", return_value=pool),
    ):
        assert infra.user_may_use_schedules(user_id=uid, user_role="user") is True
        assert infra.schedule_feature_permission_error(user_id=uid, user_role="user") is None


def test_schedule_permission_error_still_checks_min_role() -> None:
    err = schedule_permission_error(
        user_role="user",
        execution_target="security_auditor",
        user_id=uuid.uuid4(),
    )
    assert err is not None
    assert "requires admin" in err
    assert (
        schedule_permission_error(
            user_role="user",
            execution_target="general",
            user_id=uuid.uuid4(),
        )
        is None
    )
