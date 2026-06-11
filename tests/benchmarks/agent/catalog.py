"""Human-readable benchmark catalog (scenarios, fixtures, suites) for Admin UI."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from apps.backend.domain.plugin_system.tool_routing import TOOL_INTROSPECTION
from tests.benchmarks.agent.cases import SCENARIO_BY_ID, AgentScenario
from tests.benchmarks.agent.fixtures import FIXTURE_REQUIRES, OPTIONAL_FIXTURES, collect_fixture_ids
from tests.benchmarks.agent.harness import load_manifest, repo_root

_SUITE_MANIFESTS: dict[str, str] = {
    "smoke": "benchmarks/manifests/smoke.yaml",
    "workspace": "benchmarks/manifests/workspace.yaml",
    "social": "benchmarks/manifests/social.yaml",
    "integrations": "benchmarks/manifests/integrations.yaml",
    "coding": "benchmarks/manifests/coding.yaml",
    "security": "benchmarks/manifests/security.yaml",
    "dashboards": "benchmarks/manifests/dashboards.yaml",
    "full": "benchmarks/manifests/full.yaml",
}

_SUITE_LABELS: dict[str, str] = {
    "smoke": "Smoke (S1–S3)",
    "workspace": "Workspace (git + index)",
    "social": "Social (share)",
    "integrations": "Integrations (Gmail)",
    "coding": "Coding (project_run, hours)",
    "security": "Security (AgentLayer repo + SimpleSecCheck)",
    "dashboards": "Dashboards (create + layout)",
    "full": "Full regression (all domains, hours)",
}

_SUITE_DESCRIPTIONS: dict[str, str] = {
    "smoke": "Fast sanity checks: tool catalog, simple chat, read_file in self workspace.",
    "workspace": "Agent clones git workspace, reads README, searches Octocat.",
    "social": "Agent creates dashboard, block-shares to friend, confirms data.",
    "integrations": "Gmail secret fixture; skips when AGENT_BENCH_GMAIL_SECRET unset.",
    "coding": "Agent clones git workspace then coding edits (chat, long timeout).",
    "security": "Agent clones AgentLayer repo; SSC scan + remediation via tools.",
    "dashboards": "Agent creates dashboard (D1) and layout+data patch (D2).",
    "full": "All scenarios — agent does product work; fixtures only secrets/friends/self-workspace.",
}

_SCENARIO_META: dict[str, dict[str, Any]] = {
    "S1_tool_catalog": {
        "title": "Tool catalog",
        "summary": "Call a tool-catalog introspection tool and list at least three tool names.",
        "expected_tools": sorted(TOOL_INTROSPECTION),
        "rubric": "introspection tool call + non-empty reply",
    },
    "S2_simple_chat": {
        "title": "Simple chat",
        "summary": "Answer 17+25 directly; tools stay available via router but should not be required.",
        "expected_tools": [],
        "rubric": "numeric answer 42, latency < 30s",
    },
    "S3_read_file": {
        "title": "Read README",
        "summary": "read_file on README.md in AgentLayer self workspace.",
        "expected_tools": ["read_file", "repository.read_file"],
        "rubric": "read_file call + path in trace",
    },
    "W1_git_readme_no_index": {
        "title": "Git README",
        "summary": "workspace.create clone Hello-World, read_file README.md.",
        "expected_tools": ["workspace.create", "read_file"],
        "rubric": "workspace.create + read_file + workspace exists",
    },
    "W2_find_octocat_no_index": {
        "title": "Find Octocat (no index)",
        "summary": "Agent clones repo, finds Octocat via grep/read.",
        "expected_tools": ["workspace.create", "grep", "read_file", "retrieve_context"],
        "rubric": "clone + path + excerpt in reply",
    },
    "W2_find_octocat_indexed": {
        "title": "Find Octocat (indexed)",
        "summary": "Agent clones, indexes workspace, then searches.",
        "expected_tools": ["workspace.create", "index", "retrieve_context"],
        "rubric": "clone + search + excerpt",
    },
    "SOC1_block_share_visible": {
        "title": "Block share visible",
        "summary": "Agent creates dashboard, block_share_grant to friend, confirms shared_notes.",
        "expected_tools": ["create_dashboard", "block_share_grant", "dashboard.read"],
        "rubric": "reply exactly bench-visible",
    },
    "D1_dashboard_create": {
        "title": "Create dashboard",
        "summary": "create_dashboard with title {prefix}create; verified via API.",
        "expected_tools": ["create_dashboard", "dashboard.list"],
        "rubric": "dashboard exists with expected title or create_dashboard tool",
    },
    "D2_layout_patch": {
        "title": "Patch layout",
        "summary": "Agent creates dashboard, patch_layout markdown notes + patch_data bench-notes-ok.",
        "expected_tools": ["create_dashboard", "patch_layout", "patch_data"],
        "rubric": "markdown notes block + data.notes in API",
    },
    "INT1_gmail_connected": {
        "title": "Gmail connected",
        "summary": "Verify Gmail credentials stored; reply gmail-ready or explain gap.",
        "expected_tools": ["gmail", "mail"],
        "rubric": "gmail-ready or clear missing-secret message",
    },
    "C1_bench_marker_file": {
        "title": "Create bench-marker.txt",
        "summary": "Agent clones repo, writes bench-marker.txt with bench-ok.",
        "expected_tools": ["workspace.create", "write_file", "edit", "apply_patch"],
        "rubric": "clone + git change + bench-ok reply",
    },
    "C2_small_edit": {
        "title": "README small edit",
        "summary": "Chat coding agent: branch bench-c2-edit, add bench-c2-ok line to README (no push).",
        "expected_tools": ["edit", "write_file", "apply_patch", "coding_git_read"],
        "rubric": "git diff contains bench-c2-ok + write tool + reply",
    },
    "SEC1_scan_agentlayer": {
        "title": "SSC scan AgentLayer",
        "summary": "Agent clones AgentLayer repo, security_scan_resolve; reply scan_id + status.",
        "expected_tools": ["workspace.create", "security_scan_resolve", "security_scan_start"],
        "rubric": "clone + security_scan tool + scan_id/status in reply",
    },
    "SEC2_remediate_agentlayer": {
        "title": "SSC remediate AgentLayer",
        "summary": "Agent clones repo, branch, scan, SECURITY_REPORT.md, fix one LOW finding.",
        "expected_tools": ["workspace.create", "security_scan_resolve", "write_file", "edit"],
        "rubric": "clone + security tools + git changes or SECURITY_REPORT",
    },
}

_FIXTURE_META: dict[str, dict[str, Any]] = {
    "agentlayer_self": {
        "title": "AgentLayer self workspace",
        "summary": "Platform self-workspace bind for S3 (not agent-created).",
        "optional": False,
    },
    "friend_pair": {
        "title": "Friend pair",
        "summary": "Infra: ensure bench admin + user B are friends (share target email).",
        "optional": False,
    },
    "gmail_secret": {
        "title": "Gmail secret",
        "summary": "Infra: store Gmail app password via user secrets API.",
        "optional": True,
        "env_hint": "AGENT_BENCH_GMAIL_SECRET",
    },
    "ssc_secret": {
        "title": "SimpleSecCheck API key",
        "summary": "Infra: store ssc_api_key via user secrets (scan.fr4iser.com).",
        "optional": True,
        "env_hint": "AGENT_BENCH_SSC_SECRET",
    },
}


def serialize_scenario(sc: AgentScenario) -> dict[str, Any]:
    meta = _SCENARIO_META.get(sc.id, {})
    return {
        "id": sc.id,
        "tier": sc.tier,
        "title": meta.get("title") or sc.id,
        "summary": meta.get("summary") or "",
        "prompt": sc.prompt,
        "rubric": meta.get("rubric") or sc.rubric,
        "agent_id": sc.agent_id,
        "execution": sc.execution,
        "security_scan": sc.security_scan,
        "requires": list(sc.requires),
        "expected_tools": meta.get("expected_tools") or [],
        "skip_without_env": sc.skip_without_env,
    }


def serialize_fixture(fid: str) -> dict[str, Any]:
    meta = _FIXTURE_META.get(fid, {})
    return {
        "id": fid,
        "title": meta.get("title") or fid,
        "summary": meta.get("summary") or "",
        "optional": fid in OPTIONAL_FIXTURES or bool(meta.get("optional")),
        "requires": list(FIXTURE_REQUIRES.get(fid, ())),
        "env_hint": meta.get("env_hint"),
    }


def list_all_scenarios() -> list[dict[str, Any]]:
    return [serialize_scenario(sc) for sc in SCENARIO_BY_ID.values()]


def list_all_fixtures() -> list[dict[str, Any]]:
    return [serialize_fixture(fid) for fid in sorted(_FIXTURE_META)]


def fixtures_for_scenarios(
    scenario_ids: list[str],
    manifest_fixtures: list[str] | None = None,
    extra_fixtures: list[str] | None = None,
) -> list[str]:
    requires = []
    for sid in scenario_ids:
        sc = SCENARIO_BY_ID.get(sid)
        if sc:
            requires.append(sc.requires)
    ids = collect_fixture_ids(requires, (manifest_fixtures or []) + (extra_fixtures or []))
    return sorted(ids)


def describe_suite(suite_id: str) -> dict[str, Any]:
    rel = _SUITE_MANIFESTS.get(suite_id)
    if not rel:
        raise ValueError(f"unknown suite: {suite_id}")
    manifest_path = repo_root() / rel
    _, scenario_ids, tier_max, defaults, manifest_fixtures, _ = load_manifest(manifest_path)
    scenarios = []
    for sid in scenario_ids:
        sc = SCENARIO_BY_ID.get(sid)
        if sc is None:
            continue
        scenarios.append(serialize_scenario(sc))
    fixture_ids = fixtures_for_scenarios(scenario_ids, manifest_fixtures)
    return {
        "id": suite_id,
        "label": _SUITE_LABELS.get(suite_id, suite_id),
        "description": _SUITE_DESCRIPTIONS.get(suite_id, ""),
        "manifest": rel,
        "tier_max": tier_max,
        "defaults": defaults,
        "scenarios": scenarios,
        "fixtures": [serialize_fixture(fid) for fid in fixture_ids],
        "manifest_fixtures": manifest_fixtures,
    }


def list_suites_detailed() -> list[dict[str, Any]]:
    return [describe_suite(sid) for sid in _SUITE_MANIFESTS]


def catalog_payload() -> dict[str, Any]:
    return {
        "scenarios": list_all_scenarios(),
        "fixtures": list_all_fixtures(),
        "suites": list_suites_detailed(),
    }
