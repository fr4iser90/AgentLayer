from __future__ import annotations

from apps.backend.infrastructure.openai_compat_http import _normalize_chat_request_body
from apps.backend.infrastructure.openai_stream_aggregate import _prepare_json_body


def test_normalize_chat_request_merges_leading_system_messages() -> None:
    body = {
        "messages": [
            {"role": "system", "content": "System A"},
            {"role": "system", "content": "System B"},
            {"role": "user", "content": "Hi"},
        ]
    }

    normalized = _normalize_chat_request_body(body)

    assert normalized["messages"] == [
        {"role": "system", "content": "System A\n\nSystem B"},
        {"role": "user", "content": "Hi"},
    ]


def test_normalize_chat_request_converts_late_system_messages_in_place() -> None:
    body = {
        "messages": [
            {"role": "system", "content": "Initial"},
            {"role": "user", "content": "Hi"},
            {"role": "assistant", "content": "Hello"},
            {"role": "system", "content": "Runtime hint"},
            {"role": "user", "content": "Next"},
        ]
    }

    normalized = _normalize_chat_request_body(body)

    assert normalized["messages"] == [
        {"role": "system", "content": "Initial"},
        {"role": "user", "content": "Hi"},
        {"role": "assistant", "content": "Hello"},
        {"role": "user", "content": "[Server note]\nRuntime hint"},
        {"role": "user", "content": "Next"},
    ]


def test_normalize_chat_request_preserves_tool_sequence_and_original_body() -> None:
    body = {
        "messages": [
            {"role": "user", "content": "Use a tool"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [{"id": "tc1", "type": "function", "function": {"name": "x", "arguments": "{}"}}],
            },
            {"role": "tool", "tool_call_id": "tc1", "content": "{}"},
            {"role": "system", "content": "Follow-up hint"},
        ],
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "x",
                    "TOOL_DESCRIPTION": "Tool desc",
                    "parameters": {"type": "object"},
                },
            }
        ],
    }

    normalized = _normalize_chat_request_body(body)

    assert body["messages"][-1] == {"role": "system", "content": "Follow-up hint"}
    assert normalized["messages"][1]["role"] == "assistant"
    assert normalized["messages"][2]["role"] == "tool"
    assert normalized["messages"][3] == {"role": "user", "content": "[Server note]\nFollow-up hint"}
    assert "TOOL_DESCRIPTION" not in normalized["tools"][0]["function"]
    assert normalized["tools"][0]["function"]["description"] == "Tool desc"


def test_stream_prepare_json_body_normalizes_late_system_messages() -> None:
    body = {
        "messages": [
            {"role": "user", "content": "Hi"},
            {"role": "assistant", "content": "Hello"},
            {"role": "system", "content": "Runtime stream hint"},
        ],
        "stream": True,
    }

    prepared = _prepare_json_body(body)

    assert prepared["messages"] == [
        {"role": "user", "content": "Hi"},
        {"role": "assistant", "content": "Hello"},
        {"role": "user", "content": "[Server note]\nRuntime stream hint"},
    ]
