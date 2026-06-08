"""Tests for chat context preparation (trim, cap)."""

from __future__ import annotations

import asyncio

from apps.backend.infrastructure.chat_context import (
    cap_message_content,
    message_content_text,
    prepare_chat_history_for_llm,
)
from apps.backend.infrastructure.context_budget import limits_from_context_window


def test_prepare_trims_sliding_window_when_over_max(monkeypatch):
    from apps.backend.core import config as cfg

    monkeypatch.setattr(cfg.config, "CHAT_CONTEXT_PREP_ENABLED", True)
    monkeypatch.setattr(cfg.config, "CHAT_CONTEXT_COMPACTION_ENABLED", False)
    monkeypatch.setattr(cfg.config, "CHAT_CONTEXT_MAX_MESSAGES", 4)
    monkeypatch.setattr(cfg.config, "CHAT_CONTEXT_DEFAULT_BUDGET_TOKENS", 0)
    monkeypatch.setattr(cfg.config, "CHAT_CONTEXT_SOFT_LIMIT_RATIO", 0.6)
    monkeypatch.setattr(cfg.config, "CHAT_CONTEXT_HARD_LIMIT_RATIO", 0.85)

    hist = [{"role": "user" if i % 2 == 0 else "assistant", "content": f"msg {i}"} for i in range(10)]

    async def _run():
        return await prepare_chat_history_for_llm(hist)

    out, meta = asyncio.run(_run())
    assert len(out) == 4
    assert meta.messages_dropped >= 6
    assert out[-1]["content"] == "msg 9"


def test_prepare_records_messages_compacted_this_run(monkeypatch):
    import uuid

    from apps.backend.core import config as cfg

    monkeypatch.setattr(cfg.config, "CHAT_CONTEXT_PREP_ENABLED", True)
    monkeypatch.setattr(cfg.config, "CHAT_CONTEXT_COMPACTION_ENABLED", True)
    monkeypatch.setattr(cfg.config, "CHAT_CONTEXT_MAX_MESSAGES", 4)
    monkeypatch.setattr(cfg.config, "CHAT_CONTEXT_RECENT_VERBATIM_MESSAGES", 2)
    monkeypatch.setattr(cfg.config, "CHAT_CONTEXT_DEFAULT_BUDGET_TOKENS", 0)
    monkeypatch.setattr(
        "apps.backend.infrastructure.chat_context._run_compaction_llm",
        lambda **_: "summary",
    )
    monkeypatch.setattr(
        "apps.backend.infrastructure.chat_context._load_summary_state",
        lambda _cid: ("", 0),
    )
    monkeypatch.setattr(
        "apps.backend.infrastructure.chat_context._save_summary_state",
        lambda *a, **k: None,
    )

    hist = [{"role": "user" if i % 2 == 0 else "assistant", "content": f"msg {i}"} for i in range(8)]

    async def _run():
        return await prepare_chat_history_for_llm(hist, conversation_id=uuid.uuid4())

    out, meta = asyncio.run(_run())
    assert meta.compaction_applied is True
    assert meta.messages_compacted_this_run == 6
    assert len(out) == 3  # summary system + 2 recent verbatim


def test_prepare_caps_oversized_message(monkeypatch):
    from apps.backend.core import config as cfg

    monkeypatch.setattr(cfg.config, "CHAT_CONTEXT_PREP_ENABLED", True)
    monkeypatch.setattr(cfg.config, "CHAT_CONTEXT_COMPACTION_ENABLED", False)
    monkeypatch.setattr(cfg.config, "CHAT_CONTEXT_MAX_MESSAGES", 48)
    monkeypatch.setattr(cfg.config, "CHAT_CONTEXT_MAX_MESSAGE_RATIO", 0.0005)
    monkeypatch.setattr(cfg.config, "CHAT_CONTEXT_DEFAULT_BUDGET_TOKENS", 0)
    budget = limits_from_context_window(100_000, source="test")

    big = "x" * 2000

    async def _run():
        return await prepare_chat_history_for_llm(
            [{"role": "user", "content": big}],
            context_budget=budget,
        )

    out, meta = asyncio.run(_run())
    assert meta.messages_capped == 1
    assert "truncated" in message_content_text(out[0]["content"]).lower()


def test_cap_message_content():
    capped, was = cap_message_content("a" * 1000, 200)
    assert was is True
    assert len(str(capped)) < 1000
