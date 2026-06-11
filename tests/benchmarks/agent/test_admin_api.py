"""Unit tests for admin benchmark run-readiness helpers."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

from apps.backend.api.benchmarks_admin_api import _readiness_for_user, _workspace_stats_for_user


def _empty_workspace_stats() -> dict[str, int | bool]:
    return {
        "workspace_quota": 10,
        "workspace_count": 0,
        "bench_workspace_count": 0,
        "non_bench_workspace_count": 0,
        "workspace_headroom": 10,
        "has_workspace_headroom": True,
    }


def test_readiness_for_user_reports_configured_secrets() -> None:
    uid = uuid.uuid4()
    user = MagicMock()
    user.id = uid
    user.email = "bench@example.com"
    user.role = "admin"

    with (
        patch("apps.backend.api.benchmarks_admin_api.get_user_by_id", return_value=user),
        patch("apps.backend.api.benchmarks_admin_api.config") as cfg,
        patch(
            "apps.backend.api.benchmarks_admin_api._workspace_stats_for_user",
            return_value=_empty_workspace_stats(),
        ),
        patch(
            "apps.backend.api.benchmarks_admin_api.db.user_secret_list_service_keys",
            return_value=["gmail", "ssc_api_key"],
        ),
    ):
        cfg.SECRETS_MASTER_KEY = "test-key"
        out = _readiness_for_user(uid)

    assert out["email"] == "bench@example.com"
    assert out["secrets_enabled"] is True
    assert out["secrets"]["gmail"] is True
    assert out["secrets"]["ssc_api_key"] is True


def test_readiness_for_user_reports_workspace_stats() -> None:
    uid = uuid.uuid4()
    user = MagicMock()
    user.id = uid
    user.email = "bench@example.com"
    user.role = "admin"

    conn = MagicMock()
    cur = MagicMock()
    cur.fetchone.return_value = (10, 10, 2)
    conn.cursor.return_value.__enter__.return_value = cur
    pool = MagicMock()
    pool.connection.return_value.__enter__.return_value = conn

    with (
        patch("apps.backend.api.benchmarks_admin_api.get_user_by_id", return_value=user),
        patch("apps.backend.api.benchmarks_admin_api.config") as cfg,
        patch("apps.backend.api.benchmarks_admin_api.db.pool", return_value=pool),
        patch(
            "apps.backend.api.benchmarks_admin_api.db.user_secret_list_service_keys",
            return_value=[],
        ),
    ):
        cfg.SECRETS_MASTER_KEY = ""
        out = _workspace_stats_for_user(uid)

    assert out["workspace_quota"] == 10
    assert out["workspace_count"] == 10
    assert out["bench_workspace_count"] == 2
    assert out["workspace_headroom"] == 0
    assert out["has_workspace_headroom"] is False


def test_readiness_for_user_when_secrets_disabled() -> None:
    uid = uuid.uuid4()
    user = MagicMock()
    user.id = uid
    user.email = "u@example.com"
    user.role = "user"

    with (
        patch("apps.backend.api.benchmarks_admin_api.get_user_by_id", return_value=user),
        patch("apps.backend.api.benchmarks_admin_api.config") as cfg,
        patch(
            "apps.backend.api.benchmarks_admin_api._workspace_stats_for_user",
            return_value=_empty_workspace_stats(),
        ),
        patch("apps.backend.api.benchmarks_admin_api.db.user_secret_list_service_keys") as list_keys,
    ):
        cfg.SECRETS_MASTER_KEY = ""
        out = _readiness_for_user(uid)

    list_keys.assert_not_called()
    assert out["secrets_enabled"] is False
    assert out["secrets"]["gmail"] is False
