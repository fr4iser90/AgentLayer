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
    assert len(payload["fixtures"]) >= 8
    ids = {s["id"] for s in payload["scenarios"]}
    assert "S1_tool_catalog" in ids
    assert "W2_find_octocat_indexed" in ids


def test_smoke_suite_has_three_scenarios():
    suite = describe_suite("smoke")
    assert suite["id"] == "smoke"
    assert len(suite["scenarios"]) == 3
    s1 = next(s for s in suite["scenarios"] if s["id"] == "S1_tool_catalog")
    assert s1["expected_tools"]


def test_workspace_fixtures_include_git():
    suite = describe_suite("workspace")
    fixture_ids = {f["id"] for f in suite["fixtures"]}
    assert "workspace_git" in fixture_ids


def test_fixtures_for_subset_scenarios():
    ids = fixtures_for_scenarios(
        ["W2_find_octocat_indexed"],
        manifest_fixtures=["workspace_git"],
    )
    assert "workspace_git" in ids
    assert "workspace_indexed" in ids


def test_security_suite_has_sec_scenarios():
    suite = describe_suite("security")
    ids = {s["id"] for s in suite["scenarios"]}
    assert ids == {"SEC1_scan_agentlayer", "SEC2_remediate_agentlayer"}
    sec2 = next(s for s in suite["scenarios"] if s["id"] == "SEC2_remediate_agentlayer")
    assert sec2["execution"] == "project_run"
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
    }


def test_dashboards_suite_has_d1_d2():
    suite = describe_suite("dashboards")
    ids = {s["id"] for s in suite["scenarios"]}
    assert ids == {"D1_dashboard_create", "D2_layout_patch"}
    d2 = next(s for s in suite["scenarios"] if s["id"] == "D2_layout_patch")
    assert d2["agent_id"] == "dashboard"
    assert "dashboard_empty" in d2["requires"]


def test_coding_suite_has_c1_c2():
    suite = describe_suite("coding")
    ids = {s["id"] for s in suite["scenarios"]}
    assert ids == {"C1_bench_marker_file", "C2_small_edit"}
    c2 = next(s for s in suite["scenarios"] if s["id"] == "C2_small_edit")
    assert c2["agent_id"] == "coding"
    assert c2["execution"] == "chat"
