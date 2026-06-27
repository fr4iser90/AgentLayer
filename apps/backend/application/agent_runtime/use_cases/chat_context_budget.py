from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from apps.backend.application.agent_runtime.dependencies import (
    ContextPrepMeta,
    apply_agent_loop_context_budget,
    apply_budget_to_meta,
    update_meta_from_provider_usage,
)

logger = logging.getLogger(__name__)


class ChatContextBudgetEnforcer:
    def __init__(
        self,
        *,
        messages: list[dict[str, Any]],
        tool_context: dict[str, Any],
        context_prep_meta: dict[str, Any],
        model: str | None,
        event_emit: Callable[[dict[str, Any]], Awaitable[None]] | None,
        agent_run_id: str,
    ) -> None:
        self.messages = messages
        self.tool_context = tool_context
        self.context_prep_meta = context_prep_meta
        self.model = model
        self.event_emit = event_emit
        self.agent_run_id = agent_run_id

    async def emit_context_ws(
        self,
        *,
        compacted: bool = False,
        phase: str = "loop",
        reason: str = "",
        round_num: int | None = None,
    ) -> None:
        if not self.event_emit:
            return
        ctx = dict(self.tool_context.get("chat_context_meta") or {})
        await self.event_emit(
            {
                "type": "agent.context_update",
                "agent_run_id": self.agent_run_id,
                "context": ctx,
            }
        )
        if not compacted:
            return
        await self.event_emit(
            {
                "type": "agent.context_compacted",
                "agent_run_id": self.agent_run_id,
                "phase": phase,
                "reason": reason,
                "round": round_num,
                "context": ctx,
                "provider_prompt_tokens": ctx.get("provider_prompt_tokens"),
                "soft_limit_tokens": ctx.get("soft_limit_tokens"),
                "context_window_tokens": ctx.get("context_window_tokens"),
                "tool_rounds_dropped": ctx.get("tool_rounds_dropped"),
                "budget_source": ctx.get("budget_source"),
                "summary_active": ctx.get("summary_active"),
            }
        )

    async def enforce(
        self,
        reason: str,
        provider_prompt_tokens: int | None,
        *,
        round_num: int | None = None,
    ) -> None:
        budget = self.tool_context.get("_context_budget")
        new_msgs, loop_sum, patch = await apply_agent_loop_context_budget(
            self.messages,
            context_budget=budget,
            provider_prompt_tokens=provider_prompt_tokens,
            loop_summary=str(self.tool_context.get("agent_loop_context_summary") or ""),
            compaction_model=str(self.tool_context.get("_compaction_model") or self.model or ""),
            compaction_attempt=self.tool_context.get("_compaction_attempt"),
        )
        if new_msgs is not self.messages:
            self.messages[:] = new_msgs
        if loop_sum:
            self.tool_context["agent_loop_context_summary"] = loop_sum
        if provider_prompt_tokens is not None and provider_prompt_tokens > 0:
            self.tool_context["last_provider_prompt_tokens"] = provider_prompt_tokens
        compacted = bool(
            patch.get("loop_compaction_applied") or patch.get("trim_applied")
        )
        if compacted or patch:
            self.context_prep_meta.update({k: v for k, v in patch.items() if v is not None})
        if compacted:
            self.context_prep_meta["compaction_applied"] = True
            self.context_prep_meta["loop_compaction_applied"] = bool(
                patch.get("loop_compaction_applied")
            )
            logger.info("chat context budget (%s): %s", reason, patch)
        if provider_prompt_tokens is not None and budget is not None:
            meta_obj = ContextPrepMeta()
            apply_budget_to_meta(meta_obj, budget)
            update_meta_from_provider_usage(meta_obj, budget, provider_prompt_tokens)
            for key in (
                "provider_prompt_tokens",
                "at_soft_limit",
                "at_hard_limit",
            ):
                self.context_prep_meta[key] = getattr(meta_obj, key)
        self.tool_context["chat_context_meta"] = self.context_prep_meta
        if (
            compacted
            or provider_prompt_tokens is not None
            or self.context_prep_meta.get("context_window_tokens")
        ):
            await self.emit_context_ws(
                compacted=compacted,
                phase="loop",
                reason=reason,
                round_num=round_num,
            )


__all__ = ["ChatContextBudgetEnforcer"]
