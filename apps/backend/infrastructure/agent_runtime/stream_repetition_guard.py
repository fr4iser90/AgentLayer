"""Detect degenerate tail repetition in LLM assistant text (stream + non-stream)."""

from __future__ import annotations

import logging
from typing import Any

from apps.backend.infrastructure.platform.config import config

logger = logging.getLogger(__name__)


def truncate_tail_triple_repeat(
    text: str,
    *,
    min_block: int | None = None,
    repeat_count: int | None = None,
    tail_window: int | None = None,
) -> tuple[bool, str]:
    """
  If the last ``tail_window`` chars end with the same ``block`` repeated ``repeat_count``
    times in a row (``block`` length >= ``min_block``), return ``(True, truncated)`` keeping
    content through the first of those trailing copies only.
    """
    if not text:
        return False, text
    mb = min_block if min_block is not None else config.AGENT_STREAM_REPETITION_MIN_BLOCK
    rc = repeat_count if repeat_count is not None else config.AGENT_STREAM_REPETITION_REPEAT_COUNT
    tw = tail_window if tail_window is not None else config.AGENT_STREAM_REPETITION_TAIL_WINDOW
    if rc < 2:
        rc = 3
    mb = max(40, mb)
    tw = max(mb * rc, tw)

    tail = text[-tw:] if len(text) > tw else text
    prefix_len = len(text) - len(tail)
    max_block = len(tail) // rc
    if max_block < mb:
        return False, text

    for block_len in range(max_block, mb - 1, -1):
        block = tail[-block_len:]
        if not block:
            continue
        if tail.endswith(block * rc):
            new_tail = tail[: len(tail) - block_len * (rc - 1)]
            truncated = text[:prefix_len] + new_tail
            if truncated != text:
                return True, truncated
            return False, text
    return False, text


def guard_assistant_text(text: str) -> tuple[str, bool]:
    """Apply guard when enabled; return ``(text, truncated)``."""
    if not config.AGENT_STREAM_REPETITION_GUARD:
        return text, False
    aborted, truncated = truncate_tail_triple_repeat(text)
    return truncated, aborted


def apply_repetition_guard_to_completion(data: dict[str, Any]) -> bool:
    """Truncate ``choices[0].message.content`` in place when tail repetition is detected."""
    if not config.AGENT_STREAM_REPETITION_GUARD:
        return False
    try:
        choices = data.get("choices")
        if not isinstance(choices, list) or not choices:
            return False
        ch0 = choices[0]
        if not isinstance(ch0, dict):
            return False
        msg = ch0.get("message")
        if not isinstance(msg, dict):
            return False
        raw = msg.get("content")
        if not isinstance(raw, str) or not raw:
            return False
        new_text, aborted = guard_assistant_text(raw)
        if not aborted:
            return False
        msg["content"] = new_text
        ch0["finish_reason"] = "stop"
        logger.info(
            "stream repetition guard: truncated non-stream completion (%d -> %d chars)",
            len(raw),
            len(new_text),
        )
        return True
    except (TypeError, KeyError, IndexError):
        return False
