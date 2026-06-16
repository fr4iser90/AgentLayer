"""Tests for benchmark failure patterns."""

from tests.benchmarks.agent.patterns import aggregate_patterns, classify_failure


def test_classify_no_tool_call():
    p = classify_failure({"passed": False, "tools_called": []})
    assert "A1_no_tool_call" in p


def test_classify_timeout():
    p = classify_failure({"passed": False, "error": "scenario timeout after 120s"})
    assert "E_timeout" in p


def test_aggregate_patterns_counts():
    rows = [
        {"passed": False, "tools_called": []},
        {"passed": False, "error": "timeout"},
    ]
    agg = aggregate_patterns(rows)
    assert agg.get("A1_no_tool_call", 0) >= 1
    assert agg.get("E_timeout", 0) >= 1
