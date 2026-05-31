"""Tool argument normalization for retrieval / search tools."""

from apps.backend.domain.agent import _normalize_tool_call_arguments


def test_retrieve_context_fills_query_from_last_user_message():
    msgs = [{"role": "user", "content": "How does the retrieval layer work?"}]
    out = _normalize_tool_call_arguments("retrieve_context", {}, {}, msgs, None)
    assert out.get("query") == "How does the retrieval layer work?"


def test_coding_glob_fills_pattern_when_empty():
    msgs = [{"role": "user", "content": "find python files"}]
    out = _normalize_tool_call_arguments("glob", {}, {}, msgs, None)
    assert out.get("pattern") == "**/*.py"


def test_coding_search_fills_query_from_user():
    msgs = [{"role": "user", "content": "authentication middleware"}]
    out = _normalize_tool_call_arguments("search", {}, {}, msgs, None)
    assert "authentication" in (out.get("query") or "")
