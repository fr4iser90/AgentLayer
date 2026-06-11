"""Generic tool-arg normalization (unwrap only — no prose recovery)."""

from apps.backend.domain.agent import _normalize_tool_call_arguments


def test_retrieve_context_empty_without_assistant_prose():
    msgs = [{"role": "user", "content": "How does the retrieval layer work?"}]
    out = _normalize_tool_call_arguments("retrieve_context", {}, {}, msgs, None)
    assert out == {}


def test_retrieve_context_not_recovered_from_assistant_prose():
    msgs = [{"role": "user", "content": "How does the retrieval layer work?"}]
    assistant = {
        "content": 'retrieve_context({"query": "How does the retrieval layer work?"})',
    }
    out = _normalize_tool_call_arguments("retrieve_context", {}, assistant, msgs, None)
    assert out == {}


def test_glob_empty_without_assistant_prose():
    msgs = [{"role": "user", "content": "find python files"}]
    out = _normalize_tool_call_arguments("glob", {}, {}, msgs, None)
    assert out == {}
