"""Unit tests for agent completion parsing (tool_calls extraction)."""

from apps.backend.application.agent_runtime.runtime import io as agent_mod


def test_extract_tool_calls_native():
    data = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "call-1",
                            "type": "function",
                            "function": {"name": "search", "arguments": '{"gmail_query":"in:inbox"}'},
                        }
                    ],
                }
            }
        ]
    }
    _c0, _msg, tool_calls, had_native = agent_mod._extract_tool_calls_from_completion_response(
        data,
        allowed_tool_names={"search"},
    )
    assert had_native is True
    assert tool_calls is not None
    assert len(tool_calls) == 1
    assert (tool_calls[0].get("function") or {}).get("name") == "search"


def test_extract_tool_calls_empty_choices():
    data: dict = {"choices": []}
    _c0, _msg, tool_calls, had_native = agent_mod._extract_tool_calls_from_completion_response(
        data,
        allowed_tool_names=set(),
    )
    assert had_native is False
    assert tool_calls is None
