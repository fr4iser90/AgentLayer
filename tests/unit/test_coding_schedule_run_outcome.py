"""Tests for schedule run outcome evaluation and user message."""

from __future__ import annotations

from apps.backend.infrastructure.codebase import coding_schedule_execution as mod


def test_schedule_user_message_includes_doc_hints() -> None:
    msg = mod._schedule_user_message(title="Doc maintenance", doc_mode="respect")
    assert "MAINTENANCE_REPORT" in msg
    assert "DOC_PROFILE" in msg
    assert "Doc maintenance" in msg
    assert "respect" in msg


def test_evaluate_doc_job_succeeded_on_git_changes() -> None:
    status, outcome = mod._evaluate_run_status(
        tools=[],
        git_summary={"ok": True, "has_changes": True, "files": [{"path": "docs/foo.md", "stat": "1 +"}]},
        is_doc_job=True,
    )
    assert status == "succeeded"
    assert outcome == "docs_touched"


def test_evaluate_doc_job_partial_without_changes() -> None:
    status, outcome = mod._evaluate_run_status(
        tools=[{"name": "bash", "ok": False}],
        git_summary={"ok": True, "has_changes": False, "files": []},
        is_doc_job=True,
    )
    assert status == "partial"
    assert outcome == "no_doc_changes"


def test_evaluate_doc_job_succeeded_on_write_tool() -> None:
    status, outcome = mod._evaluate_run_status(
        tools=[
            {
                "name": "write_file",
                "ok": True,
                "args": {"path": "docs/MAINTENANCE_REPORT.md"},
            }
        ],
        git_summary={"ok": True, "has_changes": False, "files": []},
        is_doc_job=True,
    )
    assert status == "succeeded"
    assert outcome == "docs_touched"


def test_is_doc_maintenance_job() -> None:
    assert mod._is_doc_maintenance_job("Doc maintenance", "update docs/MAINTENANCE_REPORT.md")
    assert not mod._is_doc_maintenance_job("RSS", "fetch feeds")


def test_evaluate_failed_on_abort_reason() -> None:
    status, outcome = mod._evaluate_run_status(
        tools=[],
        git_summary=None,
        is_doc_job=True,
        abort_reason="repeated_tool_loop",
    )
    assert status == "failed"
    assert outcome == "repeated_tool_loop"


def test_evaluate_failed_on_repeated_bash_pull() -> None:
    tools = [
        {"name": "bash", "ok": True, "args": {"command": "git pull --ff-only"}},
        {"name": "bash", "ok": True, "args": {"command": "git pull --ff-only"}},
        {"name": "bash", "ok": True, "args": {"command": "git pull --ff-only"}},
    ]
    status, outcome = mod._evaluate_run_status(tools=tools, git_summary=None, is_doc_job=True)
    assert status == "failed"
    assert outcome == "repeated_git_pull"
