"""Unit tests for benchmark sandbox snapshot and cleanup reporting."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

from apps.backend.infrastructure import benchmark_resource_service as svc


def test_merge_deleted_stats_sums_all_resource_types() -> None:
    merged = svc._merge_deleted_stats(
        {"workspaces": 2, "dashboards": 3, "conversations": 4},
        {"workspaces": 1, "dashboards": 0, "conversations": 2},
    )
    assert merged == {
        "workspaces": 3,
        "dashboards": 3,
        "conversations": 6,
        "notifications": 0,
    }


def test_prepare_benchmark_sandbox_cleanup_merges_extra_deleted(monkeypatch) -> None:
    uid = uuid.uuid4()
    snap = {
        "workspace_count": 1,
        "bench_workspace_count": 0,
        "bench_dashboard_count": 0,
        "bench_conversation_count": 0,
        "benchmark_workspace_headroom": 10,
        "has_benchmark_workspace_headroom": True,
        "workspace_headroom": 9,
    }
    monkeypatch.setattr(svc, "benchmark_sandbox_snapshot", lambda *a, **k: dict(snap))
    monkeypatch.setattr(
        svc,
        "cleanup_benchmark_sandboxes",
        lambda *a, **k: {"workspaces": 0, "dashboards": 0, "conversations": 0},
    )
    out = svc.prepare_benchmark_sandbox_cleanup(
        uid,
        extra_deleted={"workspaces": 5, "dashboards": 5, "conversations": 13},
    )
    assert out["deleted"] == {
        "workspaces": 5,
        "dashboards": 5,
        "conversations": 13,
        "notifications": 0,
    }


def test_benchmark_sandbox_snapshot_includes_dashboards_and_conversations(monkeypatch) -> None:
    uid = uuid.uuid4()
    monkeypatch.setattr(
        "apps.backend.infrastructure.db.db.user_tenant_id",
        lambda _uid: 1,
    )
    monkeypatch.setattr(
        svc,
        "workspace_quota_snapshot",
        lambda *a, **k: {
            "workspace_count": 3,
            "bench_workspace_count": 2,
            "non_bench_workspace_count": 1,
            "workspace_quota": 10,
            "benchmark_workspace_quota": 10,
            "workspace_headroom": 9,
            "benchmark_workspace_headroom": 8,
            "has_workspace_headroom": True,
            "has_benchmark_workspace_headroom": True,
        },
    )

    counts = iter([(4, 3), (7, 6)])

    def _fake_count(*_a, **_k):
        return next(counts)

    monkeypatch.setattr(svc, "_count_user_bench_rows", _fake_count)
    snap = svc.benchmark_sandbox_snapshot(uid)
    assert snap["bench_dashboard_count"] == 3
    assert snap["bench_conversation_count"] == 6
    assert snap["has_bench_sandbox_resources"] is True
