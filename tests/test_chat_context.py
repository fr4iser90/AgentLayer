"""Tests for chat context preparation (trim, cap, token estimate)."""

from __future__ import annotations

import asyncio

from apps.backend.infrastructure.chat_context import (
    cap_message_content,
    estimate_tokens,
    message_content_text,
    prepare_chat_history_for_llm,
)


def test_prepare_trims_sliding_window_when_over_max(monkeypatch):
    from apps.backend.core import config as cfg

    monkeypatch.setattr(cfg.config, "CHAT_CONTEXT_PREP_ENABLED", True)
    monkeypatch.setattr(cfg.config, "CHAT_CONTEXT_COMPACTION_ENABLED", False)
    monkeypatch.setattr(cfg.config, "CHAT_CONTEXT_MAX_MESSAGES", 4)
    monkeypatch.setattr(cfg.config, "CHAT_CONTEXT_MAX_MESSAGE_CHARS", 10_000)
    monkeypatch.setattr(cfg.config, "CHAT_CONTEXT_DEFAULT_BUDGET_TOKENS", 128_000)
    monkeypatch.setattr(cfg.config, "CHAT_CONTEXT_SOFT_LIMIT_RATIO", 0.6)
    monkeypatch.setattr(cfg.config, "CHAT_CONTEXT_HARD_LIMIT_RATIO", 0.85)

    hist = [{"role": "user" if i % 2 == 0 else "assistant", "content": f"msg {i}"} for i in range(10)]

    async def _run():
        return await prepare_chat_history_for_llm(hist)

    out, meta = asyncio.run(_run())
    assert len(out) == 4
    assert meta.messages_dropped >= 6
    assert out[-1]["content"] == "msg 9"


def test_prepare_caps_oversized_message(monkeypatch):
    from apps.backend.core import config as cfg

    monkeypatch.setattr(cfg.config, "CHAT_CONTEXT_PREP_ENABLED", True)
    monkeypatch.setattr(cfg.config, "CHAT_CONTEXT_COMPACTION_ENABLED", False)
    monkeypatch.setattr(cfg.config, "CHAT_CONTEXT_MAX_MESSAGES", 48)
    monkeypatch.setattr(cfg.config, "CHAT_CONTEXT_MAX_MESSAGE_CHARS", 500)
    monkeypatch.setattr(cfg.config, "CHAT_CONTEXT_DEFAULT_BUDGET_TOKENS", 128_000)

    big = "x" * 2000

    async def _run():
        return await prepare_chat_history_for_llm([{"role": "user", "content": big}])

    out, meta = asyncio.run(_run())
    assert meta.messages_capped == 1
    assert "truncated" in message_content_text(out[0]["content"]).lower()


def test_estimate_tokens_and_cap():
    assert estimate_tokens("hello world") >= 2
    capped, was = cap_message_content("a" * 1000, 200)
    assert was is True
    assert len(str(capped)) < 1000
