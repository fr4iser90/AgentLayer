"""Unit tests for benchmark sandbox cleanup helpers."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

from tests.benchmarks.agent.bench_cleanup import (
    cleanup_prefix,
    matches_bench_prefix,
    prepare_bench_workspace_quota,
)


def test_matches_bench_prefix() -> None:
    assert matches_bench_prefix("bench-20260611T-git")
    assert not matches_bench_prefix("agentlayer-self")


def test_cleanup_prefix_delegates_to_service(monkeypatch) -> None:
    client = MagicMock()
    client.user_id = str(uuid.uuid4())
    seen: dict[str, object] = {}

    def _fake_cleanup(user_id, **kwargs):
        seen["user_id"] = user_id
        seen.update(kwargs)
        return {"workspaces": 2, "dashboards": 1, "conversations": 0}

    monkeypatch.setattr(
        "apps.backend.infrastructure.benchmarks.benchmark_resource_service.cleanup_benchmark_sandboxes",
        _fake_cleanup,
    )
    stats = cleanup_prefix(client, prefix="bench-", dry_run=False)
    assert stats["workspaces"] == 2
    assert seen["include_legacy_prefix"] is True


def test_cleanup_bench_dashboards_delegates_to_service(monkeypatch) -> None:
    client = MagicMock()
    client.user_id = str(uuid.uuid4())
    seen: dict[str, object] = {}

    def _fake_dash(user_id, **kwargs):
        seen["user_id"] = user_id
        seen.update(kwargs)
        return {"dashboards": 3, "notifications": 1}

    monkeypatch.setattr(
        "apps.backend.infrastructure.benchmarks.benchmark_resource_service.cleanup_benchmark_dashboards",
        _fake_dash,
    )
    from tests.benchmarks.agent.bench_cleanup import cleanup_bench_dashboards

    stats = cleanup_bench_dashboards(client)
    assert stats["dashboards"] == 3
    assert seen["include_legacy_prefix"] is True


def test_prepare_bench_workspace_quota_delegates(monkeypatch) -> None:
    client = MagicMock()
    client.user_id = str(uuid.uuid4())

    monkeypatch.setattr(
        "apps.backend.infrastructure.benchmarks.benchmark_resource_service.prepare_benchmark_sandbox_cleanup",
        lambda user_id, **kwargs: {
            "before": {"bench_workspace_count": 3},
            "after": {"bench_workspace_count": 0, "benchmark_workspace_headroom": 10},
            "deleted": {"workspaces": 3, "dashboards": 2, "conversations": 1},
            "has_workspace_headroom": True,
            "benchmark_workspace_headroom": 10,
            "has_benchmark_workspace_headroom": True,
        },
    )
    out = prepare_bench_workspace_quota(client, min_free=1)
    assert out["has_benchmark_workspace_headroom"] is True
    assert out["deleted"]["workspaces"] == 3
