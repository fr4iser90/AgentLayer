"""Tests for LLM tail repetition guard."""

from __future__ import annotations

from apps.backend.infrastructure.agent_runtime.stream_repetition_guard import (
    apply_repetition_guard_to_completion,
    truncate_tail_triple_repeat,
)
from apps.backend.infrastructure.agent_runtime.openai_stream_aggregate import (
    OpenAIStreamAccumulator,
    stream_accumulator_feed,
)


def test_truncate_tail_triple_repeat_detects_loop():
    block = "A" * 90 + "\n"
    text = block * 5
    aborted, truncated = truncate_tail_triple_repeat(
        text, min_block=80, repeat_count=3, tail_window=2000
    )
    assert aborted is True
    assert len(truncated) == len(block) * 3
    assert len(truncated) < len(text)


def test_truncate_tail_triple_repeat_ignores_single_block():
    text = "Hello world. " * 20
    aborted, truncated = truncate_tail_triple_repeat(
        text, min_block=80, repeat_count=3, tail_window=1500
    )
    assert aborted is False
    assert truncated == text


def test_apply_repetition_guard_to_completion_mutates():
    block = "X" * 90 + " repeated tail. "
    raw = "intro " + block * 4
    data = {"choices": [{"message": {"content": raw}, "finish_reason": None}]}
    assert apply_repetition_guard_to_completion(data) is True
    new_c = data["choices"][0]["message"]["content"]
    assert len(new_c) < len(raw)
    assert data["choices"][0]["finish_reason"] == "stop"


def test_stream_accumulator_feed_aborts_on_repetition(monkeypatch):
    from apps.backend.infrastructure.platform import config as cmod

    monkeypatch.setattr(cmod, "AGENT_STREAM_REPETITION_GUARD", True)
    block = "Z" * 85
    acc = OpenAIStreamAccumulator()
    chunk = {"choices": [{"delta": {"content": block}}]}
    for _ in range(3):
        _delta, abort_stream = stream_accumulator_feed(acc, chunk)
        if abort_stream:
            break
    assert acc.repetition_aborted is True
    assert "".join(acc._content_parts).count(block) == 1
