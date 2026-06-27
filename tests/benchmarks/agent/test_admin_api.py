"""Unit tests for admin benchmark run-readiness helpers."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

from apps.backend.api.benchmarks.controllers.benchmarks_admin_api import _readiness_for_user, _sandbox_stats_for_user


def _empty_sandbox_stats() -> dict[str, int | bool]:
    return {
        "workspace_quota": 10,
        "benchmark_workspace_quota": 10,
        "workspace_count": 0,
        "bench_workspace_count": 0,
        "non_bench_workspace_count": 0,
        "workspace_headroom": 10,
        "benchmark_workspace_headroom": 10,
        "has_workspace_headroom": True,
        "has_benchmark_workspace_headroom": True,
        "dashboard_count": 0,
        "bench_dashboard_count": 0,
        "conversation_count": 0,
        "bench_conversation_count": 0,
        "has_bench_sandbox_resources": False,
    }


def test_readiness_for_user_reports_configured_secrets() -> None:
    uid = uuid.uuid4()
    user = MagicMock()
    user.id = uid
    user.email = "bench@example.com"
    user.role = "admin"

    with (
        patch("apps.backend.api.benchmarks.controllers.benchmarks_admin_api.get_user_by_id", return_value=user),
        patch("apps.backend.api.benchmarks.controllers.benchmarks_admin_api.config") as cfg,
        patch(
            "apps.backend.api.benchmarks.controllers.benchmarks_admin_api._sandbox_stats_for_user",
            return_value=_empty_sandbox_stats(),
        ),
        patch(
            "apps.backend.api.benchmarks.controllers.benchmarks_admin_api.db.user_secret_list_service_keys",
            return_value=["gmail", "ssc_api_key"],
        ),
    ):
        cfg.SECRETS_MASTER_KEY = "test-key"
        out = _readiness_for_user(uid)

    assert out["email"] == "bench@example.com"
    assert out["secrets_enabled"] is True
    assert out["secrets"]["gmail"] is True
    assert out["secrets"]["ssc_api_key"] is True


def test_sandbox_stats_for_user_delegates_to_snapshot() -> None:
    uid = uuid.uuid4()
    snap = {
        "workspace_quota": 10,
        "benchmark_workspace_quota": 10,
        "workspace_count": 10,
        "bench_workspace_count": 2,
        "non_bench_workspace_count": 8,
        "workspace_headroom": 2,
        "benchmark_workspace_headroom": 8,
        "has_workspace_headroom": True,
        "has_benchmark_workspace_headroom": True,
        "dashboard_count": 3,
        "bench_dashboard_count": 1,
        "conversation_count": 5,
        "bench_conversation_count": 2,
        "has_bench_sandbox_resources": True,
    }

    with patch(
        "apps.backend.application.benchmarks.use_cases.benchmark_controller_services.benchmark_sandbox_snapshot",
        return_value=snap,
    ) as mock_snap:
        out = _sandbox_stats_for_user(uid)

    mock_snap.assert_called_once_with(uid, include_legacy_prefix=True)
    assert out["workspace_count"] == 10
    assert out["bench_workspace_count"] == 2
    assert out["bench_dashboard_count"] == 1


def test_readiness_for_user_when_secrets_disabled() -> None:
    uid = uuid.uuid4()
    user = MagicMock()
    user.id = uid
    user.email = "u@example.com"
    user.role = "user"

    with (
        patch("apps.backend.api.benchmarks.controllers.benchmarks_admin_api.get_user_by_id", return_value=user),
        patch("apps.backend.api.benchmarks.controllers.benchmarks_admin_api.config") as cfg,
        patch(
            "apps.backend.api.benchmarks.controllers.benchmarks_admin_api._sandbox_stats_for_user",
            return_value=_empty_sandbox_stats(),
        ),
        patch("apps.backend.api.benchmarks.controllers.benchmarks_admin_api.db.user_secret_list_service_keys") as list_keys,
    ):
        cfg.SECRETS_MASTER_KEY = ""
        out = _readiness_for_user(uid)

    list_keys.assert_not_called()
    assert out["secrets_enabled"] is False
    assert out["secrets"]["gmail"] is False
