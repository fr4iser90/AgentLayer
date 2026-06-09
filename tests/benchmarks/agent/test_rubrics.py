"""Unit tests for agent benchmark rubrics (no live server)."""

from __future__ import annotations

from tests.benchmarks.agent.rubrics import evaluate_rubric


def test_s1_passes_with_catalog_tool() -> None:
    out = evaluate_rubric(
        "s1_tool_catalog",
        content="Tools: read_file, catalog, task",
        tool_names=["catalog"],
        error=None,
    )
    assert out.passed is True
    assert out.score == 1.0


def test_s2_passes_with_42() -> None:
    out = evaluate_rubric(
        "s2_simple_chat",
        content="42",
        error=None,
        latency_ms=500.0,
    )
    assert out.passed is True


def test_s3_passes_with_read_file() -> None:
    out = evaluate_rubric(
        "s3_read_file",
        content="# AgentLayer",
        tool_names=["read_file"],
        tool_invocations=[
            {
                "tool_name": "read_file",
                "args_json": {"path": "README.md"},
                "result_excerpt": "# AgentLayer",
            }
        ],
        error=None,
    )
    assert out.passed is True


def test_w2_finds_octocat() -> None:
    out = evaluate_rubric(
        "w2_find_octocat",
        content="README mentions Octocat",
        tool_names=["read_file"],
        tool_invocations=[],
        error=None,
    )
    assert out.passed is True


def test_soc1_share_data() -> None:
    out = evaluate_rubric("soc1_share_data", content="bench-visible", error=None)
    assert out.passed is True


def test_c1_bench_marker_passes_with_git_file() -> None:
    out = evaluate_rubric(
        "c1_bench_marker",
        content="bench-ok",
        tool_names=["write_file"],
        tool_invocations=[],
        error=None,
        project_status="succeeded",
        project_summary={
            "files_changed": [{"path": "bench-marker.txt"}],
            "git": {"has_changes": True},
        },
    )
    assert out.passed is True


def test_sec1_passes_with_scan_tool_and_id() -> None:
    out = evaluate_rubric(
        "sec1_scan_agentlayer",
        content="scan_id: scan-abc123\nstatus: started",
        tool_names=["security_scan_resolve"],
        tool_invocations=[],
        error=None,
    )
    assert out.passed is True
    assert out.score == 1.0


def test_sec2_passes_with_report_and_git() -> None:
    out = evaluate_rubric(
        "sec2_remediate_agentlayer",
        content="scan_id: scan-x branch: agent/sec-bench-20260608",
        tool_names=["security_scan_resolve"],
        error=None,
        project_status="succeeded",
        project_summary={
            "tools": [
                {"name": "security_scan_resolve", "ok": True},
                {"name": "write_file", "ok": True},
            ],
            "files_changed": [{"path": "docs/SECURITY_REPORT.md"}],
            "git": {"has_changes": True},
        },
    )
    assert out.passed is True


def test_c2_passes_with_git_diff() -> None:
    out = evaluate_rubric(
        "c2_small_edit",
        content="bench-c2-ok",
        tool_names=["edit"],
        tool_invocations=[],
        error=None,
        git_changes={
            "has_changes": True,
            "stat": " README.md | 1 +\n",
            "file_diff": {"diff": "+<!-- bench-c2-ok -->\n", "has_changes": True},
        },
    )
    assert out.passed is True
    assert out.score == 1.0


def test_d1_passes_when_dashboard_exists() -> None:
    out = evaluate_rubric(
        "d1_dashboard_create",
        content="dashboard_id: abc",
        tool_names=["create_dashboard"],
        error=None,
        expected_title="bench-run-create",
        dashboard_state={"id": "abc", "title": "bench-run-create"},
    )
    assert out.passed is True


def test_d2_passes_with_notes_block() -> None:
    out = evaluate_rubric(
        "d2_layout_patch",
        content="block_added: yes",
        tool_names=["patch_layout", "patch_data"],
        error=None,
        dashboard_state={
            "ui_layout": {
                "blocks": [
                    {
                        "type": "markdown",
                        "props": {"dataPath": "notes"},
                    }
                ]
            },
            "data": {"notes": "bench-notes-ok"},
        },
    )
    assert out.passed is True
