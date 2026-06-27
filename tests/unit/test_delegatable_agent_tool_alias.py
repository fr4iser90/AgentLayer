"""Rewrite specialist agent_id aliases to delegate tool calls."""

from __future__ import annotations

from apps.backend.application.agent_runtime.runtime.tool_loop import _rewrite_delegatable_agent_tool_alias


def test_math_alias_becomes_delegate() -> None:
    out = _rewrite_delegatable_agent_tool_alias(
        "math",
        {"expression": "17 + 25"},
        allowed_names={"delegate", "catalog"},
        messages=[{"role": "user", "content": "What is 17 + 25?"}],
        caller_is_admin=True,
    )
    assert out is not None
    name, args = out
    assert name == "delegate"
    assert args["agent_id"] == "math"
    assert "17 + 25" in args["prompt"]
    assert args["run_subagent"] is True


def test_known_tool_name_not_rewritten() -> None:
    assert (
        _rewrite_delegatable_agent_tool_alias(
            "catalog",
            {},
            allowed_names={"catalog", "delegate"},
            messages=[],
            caller_is_admin=True,
        )
        is None
    )
