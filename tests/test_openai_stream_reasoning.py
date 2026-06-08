"""Stream accumulator separates content vs reasoning/thinking deltas."""

from __future__ import annotations

from apps.backend.infrastructure.openai_stream_aggregate import (
    OpenAIStreamAccumulator,
    stream_accumulator_build_completion,
    stream_accumulator_feed,
)


def _chunk(*, content: str = "", reasoning: str = "", thinking: str = "") -> dict:
    delta: dict[str, str] = {}
    if content:
        delta["content"] = content
    if reasoning:
        delta["reasoning"] = reasoning
    if thinking:
        delta["thinking"] = thinking
    return {"choices": [{"delta": delta}]}


def test_stream_accumulator_separates_content_and_reasoning():
    acc = OpenAIStreamAccumulator()
    d1, abort1 = stream_accumulator_feed(acc, _chunk(content="Hello "))
    d2, abort2 = stream_accumulator_feed(acc, _chunk(reasoning="think "))
    d3, abort3 = stream_accumulator_feed(acc, _chunk(content="world", thinking="more"))
    assert abort1 is False and abort2 is False and abort3 is False
    assert d1.content == "Hello "
    assert d1.reasoning == ""
    assert d2.content == ""
    assert d2.reasoning == "think "
    assert d3.content == "world"
    assert d3.reasoning == "more"
    out = stream_accumulator_build_completion(acc)
    msg = out["choices"][0]["message"]
    assert msg["content"] == "Hello world"
    assert msg["reasoning_content"] == "think more"


def test_stream_accumulator_reasoning_content_field():
    acc = OpenAIStreamAccumulator()
    stream_accumulator_feed(
        acc,
        {"choices": [{"delta": {"reasoning_content": "step one"}}]},
    )
    out = stream_accumulator_build_completion(acc)
    msg = out["choices"][0]["message"]
    assert msg.get("content") in ("", None)
    assert msg["reasoning_content"] == "step one"
