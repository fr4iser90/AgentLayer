"""Tests for schedules feature access (admin-only default + per-user grant)."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest

from apps.backend.domain.scheduling.access import (
    evaluate_schedules_access,
    schedule_feature_permission_error_from_flags,
)
from apps.backend.domain.scheduling.targets import schedule_permission_error
from apps.backend.infrastructure.scheduling import schedules_access as infra


def test_evaluate_site_admin_and_grant() -> None:
    assert evaluate_schedules_access(site_role="site_admin") is True
    assert evaluate_schedules_access(site_role="site_user", schedules_allowed=False) is False
    assert evaluate_schedules_access(site_role="site_user", schedules_allowed=True) is True
    assert schedule_feature_permission_error_from_flags(site_role="site_user") is not None
    assert schedule_feature_permission_error_from_flags(site_role="site_admin") is None


def test_the_rule_cannot_be_handed_a_legacy_role() -> None:
    """``users.role`` has no parameter to flow through, so no caller can offer it."""
    with pytest.raises(TypeError):
        evaluate_schedules_access(user_role="admin")  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        schedule_feature_permission_error_from_flags(user_role="admin")  # type: ignore[call-arg]


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
        assert infra.user_may_use_schedules(user_id=uid) is False
        err = infra.schedule_feature_permission_error(user_id=uid)
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
        assert infra.user_may_use_schedules(user_id=uid) is True
        assert infra.schedule_feature_permission_error(user_id=uid) is None


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
