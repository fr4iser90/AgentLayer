"""Prepare chat history for LLM prompts: cap, trim, token budget, optional compaction."""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass
from typing import Any

from apps.backend.core.config import config
from apps.backend.infrastructure.context_budget import (
    ContextBudget,
    compaction_input_max_chars_for_budget,
    message_max_chars_for_budget,
    should_compact_by_usage,
)

logger = logging.getLogger(__name__)

_SUMMARY_SYSTEM_PREFIX = (
    "[Conversation summary — older turns compacted for context budget. "
    "Use conversation_read if you need verbatim older messages.]\n\n"
)


@dataclass
class ContextPrepMeta:
    provider_prompt_tokens: int = 0
    budget_tokens: int = 0
    context_window_tokens: int = 0
    budget_source: str = ""
    soft_limit_tokens: int = 0
    hard_limit_tokens: int = 0
    soft_limit_ratio: float = 0.0
    hard_limit_ratio: float = 0.0
    messages_in_prompt: int = 0
    messages_dropped: int = 0
    messages_compacted_this_run: int = 0
    messages_capped: int = 0
    compaction_applied: bool = False
    loop_compaction_applied: bool = False
    summary_active: bool = False
    summary_covers_messages: int = 0
    at_soft_limit: bool = False
    at_hard_limit: bool = False
    tool_rounds_dropped: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "provider_prompt_tokens": self.provider_prompt_tokens,
            "budget_tokens": self.budget_tokens,
            "context_window_tokens": self.context_window_tokens,
            "budget_source": self.budget_source or None,
            "soft_limit_tokens": self.soft_limit_tokens,
            "hard_limit_tokens": self.hard_limit_tokens,
            "soft_limit_ratio": self.soft_limit_ratio,
            "hard_limit_ratio": self.hard_limit_ratio,
            "messages_in_prompt": self.messages_in_prompt,
            "messages_dropped": self.messages_dropped,
            "messages_compacted_this_run": self.messages_compacted_this_run,
            "messages_capped": self.messages_capped,
            "compaction_applied": self.compaction_applied,
            "loop_compaction_applied": self.loop_compaction_applied,
            "summary_active": self.summary_active,
            "summary_covers_messages": self.summary_covers_messages,
            "at_soft_limit": self.at_soft_limit,
            "at_hard_limit": self.at_hard_limit,
            "tool_rounds_dropped": self.tool_rounds_dropped,
        }


def apply_budget_to_meta(meta: ContextPrepMeta, budget: ContextBudget | None) -> None:
    if budget is None:
        meta.budget_tokens = 0
        meta.context_window_tokens = 0
        meta.soft_limit_tokens = 0
        meta.hard_limit_tokens = 0
        meta.soft_limit_ratio = float(config.CHAT_CONTEXT_SOFT_LIMIT_RATIO)
        meta.hard_limit_ratio = float(config.CHAT_CONTEXT_HARD_LIMIT_RATIO)
        meta.budget_source = ""
        return
    meta.budget_tokens = budget.context_window_tokens
    meta.context_window_tokens = budget.context_window_tokens
    meta.soft_limit_tokens = budget.soft_limit_tokens
    meta.hard_limit_tokens = budget.hard_limit_tokens
    meta.soft_limit_ratio = budget.soft_ratio
    meta.hard_limit_ratio = budget.hard_ratio
    meta.budget_source = budget.source


def update_meta_from_provider_usage(
    meta: ContextPrepMeta,
    budget: ContextBudget | None,
    provider_prompt_tokens: int | None,
) -> None:
    if provider_prompt_tokens is not None and provider_prompt_tokens > 0:
        meta.provider_prompt_tokens = provider_prompt_tokens
    at_soft, at_hard = should_compact_by_usage(budget, provider_prompt_tokens)
    meta.at_soft_limit = at_soft
    meta.at_hard_limit = at_hard


def message_content_text(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for p in content:
            if isinstance(p, dict):
                if p.get("type") == "text" and p.get("text"):
                    parts.append(str(p["text"]))
                elif p.get("type") == "image_url":
                    parts.append("[image]")
        return "\n".join(parts)
    if isinstance(content, dict):
        return json.dumps(content, ensure_ascii=False)
    return str(content)


def cap_message_content(content: Any, max_chars: int) -> tuple[Any, bool]:
    """Truncate oversized message bodies; preserve structure for list content."""
    if max_chars <= 0:
        return content, False
    if isinstance(content, str):
        if len(content) <= max_chars:
            return content, False
        keep = max(500, max_chars - 80)
        return content[:keep] + "\n\n…[truncated for context budget]", True
    if isinstance(content, list):
        out: list[Any] = []
        capped = False
        budget = max_chars
        for p in content:
            if not isinstance(p, dict):
                out.append(p)
                continue
            if p.get("type") == "text" and isinstance(p.get("text"), str):
                txt = p["text"]
                if len(txt) > budget:
                    keep = max(400, budget - 60)
                    out.append({**p, "text": txt[:keep] + "\n…[truncated]"})
                    capped = True
                    budget = 0
                else:
                    out.append(p)
                    budget -= len(txt)
            else:
                out.append(p)
        return out, capped
    text = message_content_text(content)
    if len(text) <= max_chars:
        return content, False
    return text[: max(500, max_chars - 80)] + "\n\n…[truncated for context budget]", True


def _normalize_history(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for m in messages:
        if not isinstance(m, dict):
            continue
        role = m.get("role")
        if role not in ("user", "assistant"):
            continue
        content = m.get("content")
        if content is None:
            continue
        text = message_content_text(content).strip()
        if not text:
            continue
        out.append({"role": role, "content": content})
    return out


def _cap_history(messages: list[dict[str, Any]], max_chars: int) -> tuple[list[dict[str, Any]], int]:
    capped_count = 0
    out: list[dict[str, Any]] = []
    for m in messages:
        new_content, was_capped = cap_message_content(m.get("content"), max_chars)
        if was_capped:
            capped_count += 1
        out.append({**m, "content": new_content})
    return out, capped_count


def _format_messages_for_compaction(messages: list[dict[str, Any]], *, max_chars: int) -> str:
    lines: list[str] = []
    used = 0
    for m in messages:
        role = str(m.get("role") or "user").upper()
        text = message_content_text(m.get("content")).strip()
        if len(text) > 4000:
            text = text[:4000] + "…"
        line = f"{role}: {text}"
        if used + len(line) > max_chars:
            lines.append("…[older messages omitted from compaction input]")
            break
        lines.append(line)
        used += len(line)
    return "\n\n".join(lines)


def _run_compaction_llm(
    *,
    existing_summary: str,
    new_block: str,
    compaction_model: str,
    compaction_attempt: tuple[str, dict[str, str], str, str] | None = None,
    compaction_max_chars: int | None = None,
) -> str:
    from apps.backend.infrastructure.llm_chat_attempt import unpack_llm_attempt
    from apps.backend.infrastructure.openai_compat_http import http_post_chat_completions

    override = (config.CHAT_CONTEXT_COMPACTION_MODEL or "").strip()
    model_id = override or compaction_model.strip()
    headers: dict[str, str] | None = None
    url = ""
    provider_id: str | None = None
    if compaction_attempt and not override:
        url, headers, attempt_model, provider_id = unpack_llm_attempt(compaction_attempt)
        if attempt_model.strip():
            model_id = attempt_model.strip()
    elif compaction_attempt and override:
        url, headers, _, provider_id = unpack_llm_attempt(compaction_attempt)
    if not url:
        logger.warning(
            "chat context compaction: no LLM transport for model %r — using text fallback",
            model_id,
        )
        return _compaction_text_fallback(existing_summary, new_block)
    if not model_id:
        return _compaction_text_fallback(existing_summary, new_block)

    user_payload = ""
    if existing_summary.strip():
        user_payload += f"Existing summary:\n{existing_summary.strip()}\n\n"
    user_payload += f"New conversation turns to merge:\n{new_block.strip()}"
    payload: dict[str, Any] = {
        "model": model_id,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You compress chat history for an AI assistant. Output markdown only. "
                    "Preserve: user goals, decisions, file paths, errors, open TODOs, preferences. "
                    "Drop: filler, repeated tool noise, greetings. Be concise."
                ),
            },
            {
                "role": "user",
                "content": user_payload[: compaction_max_chars]
                if compaction_max_chars
                else user_payload,
            },
        ],
        "stream": False,
        "temperature": 0,
        "max_tokens": 2000,
    }
    try:
        data, _ = http_post_chat_completions(
            url,
            payload,
            headers=headers,
            timeout=90.0,
            concurrency_provider_id=provider_id,
        )
        choices = data.get("choices") or []
        if choices and isinstance(choices[0], dict):
            msg = choices[0].get("message") or {}
            content = msg.get("content")
            if isinstance(content, str) and content.strip():
                return content.strip()
    except Exception as e:
        logger.warning("chat context compaction LLM failed (model=%s): %s", model_id, e)
    return _compaction_text_fallback(existing_summary, new_block)


def _compaction_text_fallback(existing_summary: str, new_block: str) -> str:
    fallback = (existing_summary.strip() + "\n\n" + new_block.strip()).strip()
    if len(fallback) > 6000:
        return fallback[:6000] + "\n…[truncated]"
    return fallback


def _load_summary_state(conversation_id: uuid.UUID) -> tuple[str, int]:
    from apps.backend.infrastructure.db import db

    try:
        with db.pool().connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT context_summary, context_summary_message_count
                    FROM chat_conversations WHERE id = %s
                    """,
                    (conversation_id,),
                )
                row = cur.fetchone()
        if not row:
            return "", 0
        summary = str(row[0] or "").strip()
        count = int(row[1] or 0)
        return summary, max(0, count)
    except Exception:
        logger.debug("context summary load failed", exc_info=True)
        return "", 0


def _save_summary_state(
    conversation_id: uuid.UUID,
    *,
    summary: str,
    message_count: int,
) -> None:
    from apps.backend.infrastructure.db import db

    try:
        with db.pool().connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE chat_conversations
                    SET context_summary = %s,
                        context_summary_message_count = %s,
                        context_summary_updated_at = now()
                    WHERE id = %s
                    """,
                    (summary, max(0, message_count), conversation_id),
                )
            conn.commit()
    except Exception:
        logger.warning("context summary save failed", exc_info=True)


def _apply_summary_prefix(summary: str, recent: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not summary.strip():
        return recent
    block = _SUMMARY_SYSTEM_PREFIX + summary.strip()
    return [{"role": "system", "content": block}, *recent]


async def prepare_chat_history_for_llm(
    messages: list[dict[str, Any]],
    *,
    conversation_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
    compaction_model: str = "",
    compaction_attempt: tuple[str, dict[str, str], str, str] | None = None,
    context_budget: ContextBudget | None = None,
    provider_prompt_tokens: int | None = None,
) -> tuple[list[dict[str, Any]], ContextPrepMeta]:
    """Cap, trim, and optionally compact stored chat history before LLM injection."""
    import asyncio

    meta = ContextPrepMeta()
    apply_budget_to_meta(meta, context_budget)
    update_meta_from_provider_usage(meta, context_budget, provider_prompt_tokens)

    if not config.CHAT_CONTEXT_PREP_ENABLED:
        meta.messages_in_prompt = len(messages)
        return list(messages), meta

    original_len = len(messages)
    hist = _normalize_history(messages)
    msg_char_cap = message_max_chars_for_budget(context_budget)
    capped_n = 0
    if msg_char_cap is not None:
        hist, capped_n = _cap_history(hist, msg_char_cap)
    meta.messages_capped = capped_n

    summary = ""
    summary_covers = 0
    if conversation_id is not None:
        summary, summary_covers = _load_summary_state(conversation_id)
        if summary_covers > len(hist):
            summary = ""
            summary_covers = 0

    recent_n = config.CHAT_CONTEXT_RECENT_VERBATIM_MESSAGES
    at_soft, _at_hard = should_compact_by_usage(context_budget, provider_prompt_tokens)

    from apps.backend.infrastructure import agent_config_effective as ace

    need_compaction = (
        ace.context_compaction_enabled()
        and conversation_id is not None
        and (len(hist) > config.CHAT_CONTEXT_MAX_MESSAGES or at_soft)
    )

    if need_compaction and len(hist) > recent_n:
        old_end = len(hist) - recent_n
        already = min(summary_covers, old_end)
        to_compact = hist[already:old_end]
        if to_compact:
            compact_cap = compaction_input_max_chars_for_budget(context_budget)
            if compact_cap is not None:
                block = _format_messages_for_compaction(to_compact, max_chars=compact_cap // 2)
                new_summary = await asyncio.to_thread(
                    _run_compaction_llm,
                    existing_summary=summary,
                    new_block=block,
                    compaction_model=compaction_model,
                    compaction_attempt=compaction_attempt,
                    compaction_max_chars=compact_cap,
                )
            else:
                block = _compaction_text_fallback(
                    summary,
                    "\n".join(
                        f"{str(m.get('role') or 'user').upper()}: {message_content_text(m.get('content'))[:500]}"
                        for m in to_compact[:20]
                    ),
                )
                new_summary = block
            summary = new_summary
            summary_covers = old_end
            if user_id is not None:
                _save_summary_state(
                    conversation_id,
                    summary=summary,
                    message_count=summary_covers,
                )
            meta.compaction_applied = True
            meta.messages_compacted_this_run = len(to_compact)
        hist = hist[-recent_n:]
    elif len(hist) > config.CHAT_CONTEXT_MAX_MESSAGES:
        dropped = len(hist) - config.CHAT_CONTEXT_MAX_MESSAGES
        meta.messages_dropped = dropped
        hist = hist[-config.CHAT_CONTEXT_MAX_MESSAGES :]

    if summary.strip() and summary_covers > 0:
        hist = _apply_summary_prefix(summary, hist)
        meta.summary_active = True
        meta.summary_covers_messages = summary_covers

    meta.messages_in_prompt = len(hist)
    meta.messages_dropped = max(meta.messages_dropped, max(0, original_len - len(hist)))

    return hist, meta
