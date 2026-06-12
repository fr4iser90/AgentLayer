"""Tests for benchmark catalog metadata."""

from __future__ import annotations

from tests.benchmarks.agent.catalog import (
    catalog_payload,
    describe_suite,
    fixtures_for_scenarios,
    list_suites_detailed,
)


def test_catalog_lists_all_scenarios_and_fixtures():
    payload = catalog_payload()
    assert len(payload["scenarios"]) >= 10
    assert len(payload["fixtures"]) == 4
    assert payload.get("available_locales") == ["de", "en"]
    ids = {s["id"] for s in payload["scenarios"]}
    assert "S1_tool_catalog" in ids
    assert "W2_find_octocat_indexed" in ids


def test_smoke_suite_has_three_scenarios():
    suite = describe_suite("smoke")
    assert suite["id"] == "smoke"
    assert len(suite["scenarios"]) == 3
    s1 = next(s for s in suite["scenarios"] if s["id"] == "S1_tool_catalog")
    assert s1["expected_tools"]


def test_workspace_suite_has_no_git_fixture():
    suite = describe_suite("workspace")
    fixture_ids = {f["id"] for f in suite["fixtures"]}
    assert fixture_ids == set()
    w1 = next(s for s in suite["scenarios"] if s["id"] == "W1_git_readme_no_index")
    assert "workspace.create" in w1["expected_tools"]


def test_fixtures_for_subset_scenarios():
    ids = fixtures_for_scenarios(["S3_read_file"], manifest_fixtures=[])
    assert ids == ["agentlayer_self"]


def test_security_suite_has_sec_scenarios():
    suite = describe_suite("security")
    ids = {s["id"] for s in suite["scenarios"]}
    assert ids == {"SEC1_scan_agentlayer", "SEC2_remediate_agentlayer"}
    sec2 = next(s for s in suite["scenarios"] if s["id"] == "SEC2_remediate_agentlayer")
    assert sec2["execution"] == "chat"
    assert sec2["security_scan"] is True


def test_list_suites_detailed_matches_manifests():
    suites = list_suites_detailed()
    assert {s["id"] for s in suites} == {
        "smoke",
        "workspace",
        "social",
        "integrations",
        "coding",
        "security",
        "dashboards",
        "full",
    }


def test_full_suite_has_all_scenarios():
    suite = describe_suite("full")
    ids = [s["id"] for s in suite["scenarios"]]
    assert len(ids) == 14
    assert ids[0] == "S1_tool_catalog"
    assert ids[-2:] == ["SEC1_scan_agentlayer", "SEC2_remediate_agentlayer"]
    fixture_ids = {f["id"] for f in suite["fixtures"]}
    assert fixture_ids == {"friend_pair", "agentlayer_self", "gmail_secret", "ssc_secret"}


def test_dashboards_suite_has_d1_d2():
    suite = describe_suite("dashboards")
    ids = {s["id"] for s in suite["scenarios"]}
    assert ids == {"D1_dashboard_create", "D2_layout_patch"}
    d2 = next(s for s in suite["scenarios"] if s["id"] == "D2_layout_patch")
    assert d2["agent_id"] == "dashboard"
    assert d2["requires"] == []


def test_coding_suite_has_c1_c2():
    suite = describe_suite("coding")
    ids = {s["id"] for s in suite["scenarios"]}
    assert ids == {"C1_bench_marker_file", "C2_small_edit"}
    c2 = next(s for s in suite["scenarios"] if s["id"] == "C2_small_edit")
    assert c2["agent_id"] == "general"
    assert c2["execution"] == "chat"
