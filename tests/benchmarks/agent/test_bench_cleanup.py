"""Unit tests for benchmark sandbox cleanup helpers."""

from __future__ import annotations

from unittest.mock import MagicMock

from tests.benchmarks.agent.bench_cleanup import (
    cleanup_prefix,
    matches_bench_prefix,
    prepare_bench_workspace_quota,
    workspace_quota_snapshot,
)


class _FakeClient:
    def __init__(
        self,
        *,
        workspaces: list[dict] | None = None,
        dashboards: list[dict] | None = None,
        me: dict | None = None,
    ) -> None:
        self.workspaces = list(workspaces or [])
        self.dashboards = list(dashboards or [])
        self.me = me or {"workspace_quota": 10}
        self.deleted: list[str] = []
        self.http = MagicMock()

    def get_json(self, path: str) -> dict:
        if path == "/v1/workspaces":
            return {"workspaces": self.workspaces}
        if path == "/v1/dashboards":
            return {"dashboards": self.dashboards}
        if path == "/v1/user/me":
            return self.me
        raise AssertionError(path)

    def _delete(self, _method: str, path: str, *, dry_run: bool, label: str) -> bool:
        del dry_run, label
        self.deleted.append(path)
        if path.startswith("/v1/workspaces/"):
            wid = path.rsplit("/", 1)[-1]
            self.workspaces = [ws for ws in self.workspaces if ws.get("id") != wid]
        return True


def test_matches_bench_prefix() -> None:
    assert matches_bench_prefix("bench-20260611T-git")
    assert not matches_bench_prefix("AgentLayer-00e2590a")


def test_workspace_quota_snapshot() -> None:
    client = _FakeClient(
        workspaces=[
            {"id": "1", "name": "bench-old-git"},
            {"id": "2", "name": "AgentLayer-abc"},
        ]
    )
    snap = workspace_quota_snapshot(client)
    assert snap == {
        "workspace_count": 2,
        "bench_workspace_count": 1,
        "non_bench_workspace_count": 1,
    }


def test_cleanup_prefix_deletes_only_bench_workspaces(monkeypatch) -> None:
    client = _FakeClient(
        workspaces=[
            {"id": "w1", "name": "bench-old-git"},
            {"id": "w2", "name": "AgentLayer-keep"},
            {"id": "w3", "name": "bench-other"},
        ]
    )
    monkeypatch.setattr(
        "tests.benchmarks.agent.bench_cleanup._delete_resource",
        lambda c, method, path, *, dry_run, label: client._delete(method, path, dry_run=dry_run, label=label),
    )
    stats = cleanup_prefix(client, prefix="bench-", dry_run=False)
    assert stats["workspaces"] == 2
    assert [ws["name"] for ws in client.workspaces] == ["AgentLayer-keep"]


def test_cleanup_prefix_run_scoped_only(monkeypatch) -> None:
    client = _FakeClient(
        workspaces=[
            {"id": "w1", "name": "bench-20260611T120000Z-git"},
            {"id": "w2", "name": "bench-20260610T120000Z-git"},
            {"id": "w3", "name": "AgentLayer-keep"},
        ]
    )
    monkeypatch.setattr(
        "tests.benchmarks.agent.bench_cleanup._delete_resource",
        lambda c, method, path, *, dry_run, label: client._delete(method, path, dry_run=dry_run, label=label),
    )
    stats = cleanup_prefix(client, prefix="bench-20260611T120000Z-", dry_run=False)
    assert stats["workspaces"] == 1
    assert sorted(ws["name"] for ws in client.workspaces) == [
        "AgentLayer-keep",
        "bench-20260610T120000Z-git",
    ]


def test_prepare_bench_workspace_quota_frees_headroom(monkeypatch) -> None:
    client = _FakeClient(
        workspaces=[{"id": f"w{i}", "name": f"bench-{i}"} for i in range(10)],
        me={"workspace_quota": 10},
    )
    monkeypatch.setattr(
        "tests.benchmarks.agent.bench_cleanup._delete_resource",
        lambda c, method, path, *, dry_run, label: client._delete(method, path, dry_run=dry_run, label=label),
    )
    out = prepare_bench_workspace_quota(client, min_free=1)
    assert out["deleted"]["workspaces"] == 10
    assert out["after"]["workspace_count"] == 0
    assert out["workspace_headroom"] == 10
    assert out["has_workspace_headroom"] is True
