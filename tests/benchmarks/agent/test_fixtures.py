"""Unit tests for benchmark fixture dependency resolution."""

from __future__ import annotations

from tests.benchmarks.agent.cases import SCENARIO_BY_ID
from tests.benchmarks.agent.fixtures import (
    FIXTURE_REQUIRES,
    FixtureContext,
    _topo_sort,
    dashboard_id_for_scenario,
    workspace_id_for_scenario,
)


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


def test_workspace_id_for_scenario_picks_fixture_specific_workspace() -> None:
    ctx = FixtureContext(
        run_id="r1",
        prefix="bench-r1-",
        workspace_id="last-wins",
        workspace_by_fixture={
            "agentlayer_self": "self-ws",
            "workspace_git": "git-ws",
            "workspace_agentlayer_git": "sec-ws",
        },
    )
    s3 = SCENARIO_BY_ID["S3_read_file"]
    c2 = SCENARIO_BY_ID["C2_small_edit"]
    sec1 = SCENARIO_BY_ID["SEC1_scan_agentlayer"]
    assert workspace_id_for_scenario(ctx, s3.requires) == "self-ws"
    assert workspace_id_for_scenario(ctx, c2.requires) == "git-ws"
    assert workspace_id_for_scenario(ctx, sec1.requires) == "sec-ws"


def test_dashboard_id_for_scenario_picks_fixture_specific_dashboard() -> None:
    ctx = FixtureContext(
        run_id="r1",
        prefix="bench-r1-",
        dashboard_id="last-wins",
        dashboard_by_fixture={
            "dashboard_empty": "dash-empty",
            "dashboard_block_share": "dash-share",
        },
    )
    d2 = SCENARIO_BY_ID["D2_layout_patch"]
    soc1 = SCENARIO_BY_ID["SOC1_block_share_visible"]
    assert dashboard_id_for_scenario(ctx, d2.requires, agent_id=d2.agent_id) == "dash-empty"
    assert dashboard_id_for_scenario(ctx, soc1.requires, agent_id=soc1.agent_id) == "dash-share"
