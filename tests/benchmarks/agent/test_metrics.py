"""Tests for benchmark run metrics extraction."""

from __future__ import annotations

from tests.benchmarks.agent.metrics import build_run_metrics, summarize_ws_events


def test_summarize_compaction_events() -> None:
    events = [
        {"type": "agent.context_update"},
        {
            "type": "agent.context_compacted",
            "phase": "loop",
            "reason": "soft_limit",
            "round": 3,
            "provider_prompt_tokens": 12000,
        },
        {"type": "agent.tool_done", "name": "read_file", "ok": True},
        {"type": "agent.tool_done", "name": "bash", "ok": False},
        {"type": "agent.llm_round", "round": 4},
    ]
    compactions, timeline, counts = summarize_ws_events(events)
    assert len(compactions) == 1
    assert compactions[0]["phase"] == "loop"
    assert counts["tool_fail_count"] == 1
    assert counts["llm_round_count"] == 1


def test_build_run_metrics_merges_context_and_trace() -> None:
    completion = {
        "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
        "agentlayer_context": {
            "compaction_applied": True,
            "loop_compaction_applied": True,
            "messages_compacted_this_run": 8,
            "provider_prompt_tokens": 9000,
            "budget_tokens": 10000,
            "at_soft_limit": True,
        },
    }
    invocations = [{"tool_name": "grep", "ok": True}]
    metrics = build_run_metrics(
        completion=completion,
        ws_events=None,
        tool_invocations=invocations,
        agent_run={"status": "succeeded", "token_usage": {"total_tokens": 150}},
        capture_mode="http",
    )
    assert metrics.compaction_count >= 1
    assert metrics.context_snapshot.get("messages_compacted_this_run") == 8
    assert metrics.context_utilization_pct == 90.0
    assert metrics.total_tokens == 150
