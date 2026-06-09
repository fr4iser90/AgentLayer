"""OpenAI chat/completions routing tuple: url, headers, model, catalog provider id."""

from __future__ import annotations

from typing import TypeAlias

LlmChatAttempt: TypeAlias = tuple[str, dict[str, str], str, str]


def make_llm_attempt(
    url: str,
    headers: dict[str, str],
    model: str,
    provider_id: str,
) -> LlmChatAttempt:
    return (url, headers, model, (provider_id or "").strip())


def unpack_llm_attempt(raw: tuple) -> LlmChatAttempt:
    if len(raw) >= 4:
        return raw[0], raw[1], raw[2], str(raw[3] or "")
    if len(raw) == 3:
        return raw[0], raw[1], raw[2], ""
    raise ValueError(f"invalid LLM attempt tuple length {len(raw)}")
