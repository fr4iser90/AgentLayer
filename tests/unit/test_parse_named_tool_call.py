from apps.backend.domain.agent_io import _parse_named_parenthesized_tool_call


def test_parse_named_parenthesized_tool_call():
    text = 'Planning bind({"workspace_id": "x"}) next.'
    assert _parse_named_parenthesized_tool_call(text, "bind") == {"workspace_id": "x"}
