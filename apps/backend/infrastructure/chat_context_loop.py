"""Mid-run context compaction driven by provider ``usage.prompt_tokens``."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from apps.backend.core.config import config
from apps.backend.infrastructure.chat_context import (
    _cap_history,
    _compaction_text_fallback,
    _format_messages_for_compaction,
    _run_compaction_llm,
    cap_message_content,
)
from apps.backend.infrastructure.context_budget import (
    ContextBudget,
    compaction_input_max_chars_for_budget,
    message_max_chars_for_budget,
    should_compact_by_usage,
    tool_result_max_chars_for_budget,
)

logger = logging.getLogger(__name__)

_OMIT_NOTE = (
    "[Context budget — older tool rounds compacted (provider prompt_tokens over soft limit). "
    "Use conversation_read for verbatim history or re-run tools if needed.]\n\n"
)


def _find_tool_round_groups(messages: list[dict[str, Any]]) -> tuple[int, list[list[int]]]:
    groups: list[list[int]] = []
    first_group_start = len(messages)
    i = 0
    while i < len(messages):
        m = messages[i]
        if isinstance(m, dict) and m.get("role") == "assistant" and m.get("tool_calls"):
            if not groups:
                first_group_start = i
            idxs = [i]
            i += 1
            while i < len(messages) and isinstance(messages[i], dict) and messages[i].get("role") == "tool":
                idxs.append(i)
                i += 1
            while i < len(messages) and isinstance(messages[i], dict) and messages[i].get("role") == "system":
                idxs.append(i)
                i += 1
            groups.append(idxs)
        else:
            i += 1
    return first_group_start, groups


def _rebuild_with_kept_indices(
    messages: list[dict[str, Any]],
    *,
    keep_indices: set[int],
    insert_after: int,
    note: str,
) -> list[dict[str, Any]]:
    ordered = [messages[i] for i in range(len(messages)) if i in keep_indices]
    if note.strip():
        prefix_kept = sum(1 for i in range(insert_after) if i in keep_indices)
        ordered.insert(prefix_kept, {"role": "system", "content": note.strip()})
    return ordered


def _cap_tool_and_oversized_messages(
    messages: list[dict[str, Any]],
    *,
    context_budget: ContextBudget | None = None,
) -> tuple[list[dict[str, Any]], int]:
    out: list[dict[str, Any]] = []
    capped = 0
    tool_max = tool_result_max_chars_for_budget(context_budget)
    msg_max = message_max_chars_for_budget(context_budget)
    if tool_max is None or msg_max is None:
        return list(messages), 0
    for m in messages:
        if not isinstance(m, dict):
            continue
        mm = dict(m)
        role = mm.get("role")
        limit = tool_max if role == "tool" else msg_max
        new_content, was = cap_message_content(mm.get("content"), limit)
        if was:
            capped += 1
            mm["content"] = new_content
        out.append(mm)
    return out, capped


async def apply_agent_loop_context_budget(
    messages: list[dict[str, Any]],
    *,
    context_budget: ContextBudget | None,
    provider_prompt_tokens: int | None,
    loop_summary: str = "",
    compaction_model: str = "",
    compaction_attempt: tuple[str, dict[str, str], str, str] | None = None,
) -> tuple[list[dict[str, Any]], str, dict[str, Any]]:
    """Compact tool transcript when provider-reported prompt tokens exceed soft ratio."""
    patch: dict[str, Any] = {
        "trim_applied": False,
        "tool_rounds_dropped": 0,
        "messages_capped": 0,
        "loop_compaction_applied": False,
    }
    if not config.CHAT_CONTEXT_PREP_ENABLED:
        return list(messages), loop_summary, patch

    from apps.backend.infrastructure import agent_config_effective as ace

    if not ace.context_agent_loop_trim_enabled():
        return list(messages), loop_summary, patch

    at_soft, at_hard = should_compact_by_usage(context_budget, provider_prompt_tokens)
    patch["provider_prompt_tokens"] = provider_prompt_tokens or 0
    if context_budget is not None:
        patch["context_window_tokens"] = context_budget.context_window_tokens
        patch["soft_limit_tokens"] = context_budget.soft_limit_tokens
        patch["hard_limit_tokens"] = context_budget.hard_limit_tokens
        patch["at_soft_limit"] = at_soft
        patch["at_hard_limit"] = at_hard

    msgs, capped_n = _cap_tool_and_oversized_messages(messages, context_budget=context_budget)
    patch["messages_capped"] = capped_n

    if context_budget is None:
        if provider_prompt_tokens:
            logger.warning(
                "chat context: provider prompt_tokens=%d but no model context window — "
                "set provider metadata or CHAT_CONTEXT_MODEL_BUDGET_OVERRIDES",
                provider_prompt_tokens,
            )
        return msgs, loop_summary, patch

    if not at_soft:
        return msgs, loop_summary, patch

    prefix_len, groups = _find_tool_round_groups(msgs)
    if not groups:
        if at_soft:
            half_msg = message_max_chars_for_budget(context_budget)
            cap = (half_msg // 2) if half_msg else None
            if cap is None:
                return msgs, loop_summary, patch
            tighter, extra = _cap_history(msgs, cap)
            patch["messages_capped"] += extra
            patch["trim_applied"] = extra > 0
            patch["loop_compaction_applied"] = extra > 0
            return tighter, loop_summary, patch
        return msgs, loop_summary, patch

    keep = ace.context_keep_recent_tool_rounds()
    if at_hard:
        keep = max(2, keep // 2)

    dropped_total = 0
    summary = loop_summary.strip()
    while groups and len(groups) > keep:
        if not should_compact_by_usage(context_budget, provider_prompt_tokens)[0] and dropped_total > 0:
            break
        drop_n = max(1, len(groups) - keep)
        to_drop_groups = groups[:drop_n]
        groups = groups[drop_n:]
        drop_indices: set[int] = set()
        for g in to_drop_groups:
            drop_indices.update(g)
        dropped_msgs = [msgs[i] for i in sorted(drop_indices)]
        compact_cap = compaction_input_max_chars_for_budget(context_budget)
        if compact_cap is None:
            continue
        block = _format_messages_for_compaction(dropped_msgs, max_chars=compact_cap // 2)
        if ace.context_compaction_enabled() and compaction_attempt:
            summary = await asyncio.to_thread(
                _run_compaction_llm,
                existing_summary=summary,
                new_block=block,
                compaction_model=compaction_model,
                compaction_attempt=compaction_attempt,
                compaction_max_chars=compact_cap,
            )
        else:
            summary = _compaction_text_fallback(summary, block)
        keep_indices = set(range(prefix_len))
        for g in groups:
            keep_indices.update(g)
        note_cap = compact_cap or compaction_input_max_chars_for_budget(context_budget)
        note = (_OMIT_NOTE + summary.strip())[: note_cap] if note_cap else (_OMIT_NOTE + summary.strip())
        msgs = _rebuild_with_kept_indices(
            msgs,
            keep_indices=keep_indices,
            insert_after=prefix_len,
            note=note,
        )
        prefix_len, groups = _find_tool_round_groups(msgs)
        dropped_total += drop_n
        patch["trim_applied"] = True
        patch["loop_compaction_applied"] = True

    patch["tool_rounds_dropped"] = dropped_total
    if dropped_total:
        logger.info(
            "chat context: loop compacted provider_prompt_tokens=%s tool_rounds_dropped=%d "
            "soft=%d window=%d source=%s",
            provider_prompt_tokens,
            dropped_total,
            context_budget.soft_limit_tokens,
            context_budget.context_window_tokens,
            context_budget.source,
        )
    return msgs, summary, patch
