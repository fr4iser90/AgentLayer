"""Failure export must include self-contained diagnostic report (no trace UI)."""

from __future__ import annotations

from tests.benchmarks.agent.metrics import (
    build_failure_export_report,
    extract_subagent_activity_from_ws,
)


def test_extract_subagent_activity_from_ws() -> None:
    events = [
        {
            "type": "agent.subagent_start",
            "subagent_run_id": "sub-1",
            "agent_id": "coding",
        },
        {
            "type": "agent.subagent_step",
            "subagent_run_id": "sub-1",
            "agent_id": "coding",
            "tool": "repository.read_file",
            "phase": "start",
            "round": 1,
        },
        {
            "type": "agent.subagent_step",
            "subagent_run_id": "sub-1",
            "agent_id": "coding",
            "tool": "repository.read_file",
            "phase": "done",
            "ok": True,
            "round": 1,
        },
    ]
    subs = extract_subagent_activity_from_ws(events)
    assert len(subs) == 1
    assert subs[0]["agent_id"] == "coding"
    assert len(subs[0]["steps"]) == 2


def test_build_failure_export_report_timeout_during_subagent() -> None:
    diag = {
        "tool_rounds": [
            {"round": 1, "name": "workspace.create", "ok": True, "normalized_arguments": {"name": "bench-ws"}},
            {"round": 2, "name": "delegate", "summary": "coding task"},
        ],
        "timeline_tail": [
            {"type": "agent.tool_done", "tool": "workspace.create", "ok": True},
            {"type": "agent.subagent_start", "agent_id": "coding", "subagent_run_id": "sub-x"},
            {
                "type": "agent.subagent_step",
                "agent_id": "coding",
                "subagent_run_id": "sub-x",
                "tool": "bash",
                "phase": "start",
            },
        ],
        "event_counts": {"subagent_start_count": 1, "llm_round_count": 2},
        "subagents": [
            {
                "agent_id": "coding",
                "subagent_run_id": "sub-x",
                "steps": [{"tool": "bash", "phase": "start"}],
            }
        ],
        "blocked_phase": "subagent_tool",
        "blocked_detail": "bash (start)",
        "insights": ["Run ended before chat.completion (timeout or cancel)."],
        "llm_stream": {"reasoning": "I will create the marker file using bash..."},
    }
    report = build_failure_export_report(
        diag,
        transport_error="scenario timeout after 360s",
        rubric_failure="bench-ok not in reply",
        assistant_excerpt="planning...",
    )
    assert "360s" in report["summary"]
    assert report["blocked_phase"] == "subagent_tool"
    assert report["subagents"][0]["agent_id"] == "coding"
    assert report["parent_tool_rounds"][0]["name"] == "workspace.create"
    assert report["llm_stream_tail"]
