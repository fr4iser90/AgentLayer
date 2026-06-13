"""Headroom flags on prepare_benchmark_sandbox_cleanup output."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

from apps.backend.infrastructure import benchmark_resource_service as svc


def test_prepare_cleanup_reports_no_bench_headroom(monkeypatch) -> None:
    uid = uuid.uuid4()
    full = {
        "workspace_count": 10,
        "bench_workspace_count": 10,
        "workspace_headroom": 0,
        "benchmark_workspace_headroom": 0,
        "has_workspace_headroom": False,
        "has_benchmark_workspace_headroom": False,
    }
    monkeypatch.setattr(svc, "benchmark_sandbox_snapshot", lambda *a, **k: dict(full))
    monkeypatch.setattr(
        svc,
        "cleanup_benchmark_sandboxes",
        lambda *a, **k: {"workspaces": 0, "dashboards": 0, "conversations": 0},
    )
    out = svc.prepare_benchmark_sandbox_cleanup(uid, min_free=1)
    assert out["has_benchmark_workspace_headroom"] is False
    assert out["has_workspace_headroom"] is False
