"""Unit tests for benchmark fixture dependency resolution."""

from __future__ import annotations

from tests.benchmarks.agent.cases import SCENARIO_BY_ID
from tests.benchmarks.agent.fixtures import (
    FIXTURE_REQUIRES,
    FixtureContext,
    _topo_sort,
    workspace_id_for_scenario,
)


def test_topo_sort_orders_dependencies() -> None:
    ordered = _topo_sort({"friend_pair", "ssc_secret"})
    assert ordered.index("friend_pair") < ordered.index("ssc_secret") or "ssc_secret" in ordered


def test_fixture_requires_keys_registered() -> None:
    for fid in ("agentlayer_self", "friend_pair", "gmail_secret", "ssc_secret"):
        assert fid in FIXTURE_REQUIRES


def test_workspace_id_for_scenario_only_self_workspace() -> None:
    ctx = FixtureContext(run_id="r1", prefix="bench-r1-", workspace_id="self-ws")
    s3 = SCENARIO_BY_ID["S3_read_file"]
    w1 = SCENARIO_BY_ID["W1_git_readme_no_index"]
    assert workspace_id_for_scenario(ctx, s3.requires) == "self-ws"
    assert workspace_id_for_scenario(ctx, w1.requires) is None
