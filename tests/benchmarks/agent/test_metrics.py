"""Tests for benchmark run metrics extraction."""

from __future__ import annotations

from tests.benchmarks.agent.metrics import (
    bench_ws_diagnostics,
    build_run_metrics,
    extract_llm_stream_from_ws,
    extract_schema_rounds_from_ws,
    extract_tool_rounds_from_ws,
    live_snapshot_from_ws_events,
    summarize_ws_events,
)


def test_extract_llm_stream_from_ws_reconstructs_channels() -> None:
    events = [
        {"type": "agent.llm_delta", "round": 1, "channel": "reasoning", "reasoning_delta": "think "},
        {"type": "agent.llm_delta", "round": 1, "channel": "reasoning", "reasoning_delta": "hard"},
        {"type": "agent.llm_delta", "round": 1, "delta": "Hello"},
        {"type": "agent.llm_delta", "round": 1, "delta": " world"},
    ]
    stream = extract_llm_stream_from_ws(events)
    assert stream["reasoning"] == "think hard"
    assert stream["text"] == "Hello world"
    assert stream["reasoning_chars"] == 10
    assert stream["text_chars"] == 11
    assert stream["last_round"] == 1
    diag = bench_ws_diagnostics(events)
    assert diag["llm_stream"]["text"] == "Hello world"


def test_bench_ws_diagnostics_collects_errors_and_timeline() -> None:
    events = [
        {"type": "agent.llm_round", "round": 1},
        {"type": "error", "detail": "upstream failed", "http_status": 502},
    ]
    diag = bench_ws_diagnostics(events)
    assert diag["ws_event_count"] == 2
    assert diag["ws_errors"][-1]["detail"] == "upstream failed"
    assert diag["event_counts"]["llm_round_count"] == 1


def test_extract_tool_rounds_pairs_start_done_and_insights() -> None:
    events = [
        {"type": "agent.tool_start", "round": 1, "name": "create_dashboard", "summary": "(empty)"},
        {"type": "agent.tool_done", "round": 1, "name": "create_dashboard", "result_ok": True},
        {"type": "agent.tool_start", "round": 2, "name": "create_dashboard", "summary": "(empty)"},
        {"type": "agent.tool_done", "round": 2, "name": "create_dashboard", "result_ok": True},
        {
            "type": "agent.tool_start",
            "round": 3,
            "name": "bash",
            "summary": "rejected: empty or invalid arguments",
            "rejected": True,
            "wire_arguments": "{}",
            "validation": {
                "missing_or_empty": ["command"],
                "schema_required": ["command"],
                "received_arguments": {},
            },
        },
        {
            "type": "agent.tool_done",
            "round": 3,
            "name": "bash",
            "result_ok": False,
            "result_error": "missing command",
            "promoted_full_schema": True,
        },
        {
            "type": "agent.llm_round_start",
            "round": 4,
            "full_schema_tools": ["bash"],
        },
    ]
    rounds = extract_tool_rounds_from_ws(events)
    assert len(rounds) == 3
    assert rounds[0]["summary"] == "(empty)"
    assert rounds[2]["rejected"] is True
    assert rounds[2]["wire_arguments"] == "{}"
    assert rounds[2]["validation"]["missing_or_empty"] == ["command"]
    assert rounds[2]["promoted_full_schema"] is True
    schema_rounds = extract_schema_rounds_from_ws(events)
    assert schema_rounds == [{"round": 4, "full_schema_tools": ["bash"]}]
    diag = bench_ws_diagnostics(events, error="scenario timeout after 180s")
    assert diag["tool_rounds"][0]["name"] == "create_dashboard"
    assert any("wire=" in line for line in diag["insights"])
    assert any("missing=command" in line for line in diag["insights"])
    assert any("full schema forwarded" in line for line in diag["insights"])
    assert any("timeout" in line.lower() for line in diag["insights"])
    assert not any(
        "create_dashboard" in line and "rejected or failed" in line for line in diag["insights"]
    )


def test_live_snapshot_from_ws_events() -> None:
    events = [
        {"type": "agent.llm_round", "round": 1},
        {"type": "agent.tool_start", "name": "catalog"},
        {"type": "agent.tool_done", "name": "catalog", "ok": True},
    ]
    snap = live_snapshot_from_ws_events(events, elapsed_ms=1234.5)
    assert snap["phase"] == "tool"
    assert snap["detail"] == "catalog"
    assert snap["llm_round_count"] == 1
    assert snap["tool_call_count"] == 1
    assert snap["tool_names"] == ["catalog"]
    assert snap["elapsed_ms"] == 1234.5


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
        {"type": "agent.tool_done", "name": "read_file", "result_ok": True},
        {"type": "agent.tool_done", "name": "bash", "result_ok": False},
        {"type": "agent.llm_round", "round": 4},
    ]
    compactions, timeline, counts = summarize_ws_events(events)
    assert len(compactions) == 1
    assert compactions[0]["phase"] == "loop"
    assert counts["tool_fail_count"] == 1
    assert counts["llm_round_count"] == 1


def test_summarize_collapses_llm_delta_chunks() -> None:
    events = [
        {"type": "agent.llm_round_start", "round": 1},
        {"type": "agent.llm_delta", "round": 1, "channel": "reasoning", "reasoning_delta": "a"},
        {"type": "agent.llm_delta", "round": 1, "channel": "reasoning", "reasoning_delta": "bc"},
        {"type": "agent.llm_delta", "round": 1, "delta": "Hi"},
        {"type": "agent.llm_delta", "round": 1, "delta": " there"},
        {"type": "agent.llm_round", "round": 1},
    ]
    _, timeline, _ = summarize_ws_events(events)
    delta_rows = [row for row in timeline if row.get("type") == "agent.llm_delta"]
    assert len(delta_rows) == 2
    reasoning = next(row for row in delta_rows if row.get("channel") == "reasoning")
    text = next(row for row in delta_rows if row.get("channel") == "text")
    assert reasoning["delta_chars"] == 3
    assert reasoning["delta_events"] == 2
    assert text["delta_chars"] == 8
    assert text["delta_events"] == 2
    assert [row.get("type") for row in timeline] == [
        "agent.llm_round_start",
        "agent.llm_delta",
        "agent.llm_delta",
        "agent.llm_round",
    ]


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


def test_build_run_metrics_cached_prompt_tokens() -> None:
    metrics = build_run_metrics(
        completion={
            "usage": {
                "prompt_tokens": 5000,
                "completion_tokens": 10,
                "prompt_tokens_details": {"cached_tokens": 4800},
            }
        },
        ws_events=None,
        tool_invocations=[],
        agent_run=None,
        capture_mode="websocket",
        provider_cache_prompt_disabled=True,
    )
    assert metrics.provider_cached_prompt_tokens == 4800
    assert metrics.provider_cache_prompt_disabled is True

def test_live_snapshot_shows_llm_generating_on_round_start() -> None:
    events = [{"type": "agent.llm_round_start", "round": 1}]
    snap = live_snapshot_from_ws_events(events, elapsed_ms=500.0)
    assert snap["phase"] == "llm_generating"
    assert snap["detail"] == "round 1"
    assert snap["current_llm_round"] == 1
    assert snap["llm_round_count"] == 0


def test_live_snapshot_session_tools_and_reasoning_preview() -> None:
    events = [
        {
            "type": "agent.session",
            "forwarded_tools": ["catalog", "read_file"],
            "routed_category": "minimal",
        },
        {"type": "agent.llm_round_start", "round": 1},
        {
            "type": "agent.llm_delta",
            "round": 1,
            "channel": "reasoning",
            "reasoning_delta": "Let me compute 17+25 step by step",
        },
    ]
    snap = live_snapshot_from_ws_events(events, elapsed_ms=1200.0)
    assert snap["forwarded_tool_count"] == 2
    assert snap["routed_category"] == "minimal"
    assert snap["phase"] == "llm_generating"
    assert snap["llm_reasoning_chars"] == 33
    assert "17+25" in snap.get("generation_preview", "")

