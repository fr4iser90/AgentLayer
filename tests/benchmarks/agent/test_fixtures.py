"""Unit tests for benchmark fixture dependency resolution."""

from __future__ import annotations

from tests.benchmarks.agent.fixtures import FIXTURE_REQUIRES, _topo_sort


def test_topo_sort_orders_dependencies() -> None:
    ordered = _topo_sort({"dashboard_block_share", "workspace_indexed", "workspace_git"})
    assert ordered.index("workspace_git") < ordered.index("workspace_indexed")
    assert ordered.index("friend_pair") < ordered.index("dashboard_block_share")


def test_topo_sort_workspace_chain() -> None:
    ordered = _topo_sort({"workspace_indexed", "workspace_git"})
    assert ordered == ["workspace_git", "workspace_indexed"]


def test_fixture_requires_keys_registered() -> None:
    for fid in (
        "agentlayer_self",
        "workspace_git",
        "workspace_indexed",
        "friend_pair",
        "dashboard_block_share",
        "gmail_secret",
    ):
        assert fid in FIXTURE_REQUIRES
