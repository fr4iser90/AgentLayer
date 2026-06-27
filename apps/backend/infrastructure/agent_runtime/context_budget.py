"""Context window resolution (provider metadata) and per-completion quota slices.

All completion quotas are **ratios × provider context window** — no fixed token
ceilings. Configure ratios in ``apps/backend/infrastructure/config.py`` / ``.env``.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from apps.backend.infrastructure.platform.config import config

logger = logging.getLogger(__name__)

# Rough chars/token for cap limits derived from token quotas (OpenAI-style English).
CHARS_PER_TOKEN_ESTIMATE = 4

# llama.cpp OpenAI server exposes runtime window as ``meta.n_ctx`` (not top-level
# ``context_length``). ``n_ctx_train`` is a fallback when ``n_ctx`` is absent.
_CONTEXT_LENGTH_KEYS = (
    "context_length",
    "max_context_length",
    "max_model_len",
    "n_ctx",
    "n_ctx_train",
    "context_window",
)


def _positive_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and value > 0:
        return value
    if isinstance(value, float) and value > 0:
        return int(value)
    if isinstance(value, str):
        s = value.strip()
        if s.isdigit():
            return int(s)
    return None


def extract_context_length_from_model_item(item: dict[str, Any]) -> int | None:
    """Best-effort context window from provider ``/v1/models`` row (Ollama, llama.cpp, …)."""
    for key in _CONTEXT_LENGTH_KEYS:
        n = _positive_int(item.get(key))
        if n:
            return n
    for nested_key in ("model_info", "details", "meta", "metadata"):
        nested = item.get(nested_key)
        if not isinstance(nested, dict):
            continue
        for key in _CONTEXT_LENGTH_KEYS:
            n = _positive_int(nested.get(key))
            if n:
                return n
        for nk, nv in nested.items():
            if isinstance(nk, str) and "context" in nk.lower():
                n = _positive_int(nv)
                if n:
                    return n
    return None


def _model_budget_overrides() -> dict[str, int]:
    raw = (getattr(config, "CHAT_CONTEXT_MODEL_BUDGET_OVERRIDES", None) or "").strip()
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("CHAT_CONTEXT_MODEL_BUDGET_OVERRIDES is not valid JSON")
        return {}
    if not isinstance(data, dict):
        return {}
    out: dict[str, int] = {}
    for k, v in data.items():
        mid = str(k or "").strip()
        n = _positive_int(v)
        if mid and n:
            out[mid] = n
    return out


@dataclass(frozen=True)
class ContextBudget:
    context_window_tokens: int
    soft_limit_tokens: int
    hard_limit_tokens: int
    source: str  # provider_catalog | operator_override | operator_fallback

    @property
    def soft_ratio(self) -> float:
        if self.context_window_tokens <= 0:
            return 0.0
        return self.soft_limit_tokens / self.context_window_tokens

    @property
    def hard_ratio(self) -> float:
        if self.context_window_tokens <= 0:
            return 0.0
        return self.hard_limit_tokens / self.context_window_tokens


def _quota_tokens(context_window_tokens: int, ratio: float) -> int:
    """Token slice = ``ratio × provider context window`` (minimum 1 when window > 0)."""
    window = max(1, int(context_window_tokens))
    r = max(0.0, min(1.0, float(ratio)))
    return max(1, int(window * r))


def _quota_chars_from_tokens(token_quota: int) -> int:
    return max(1, int(token_quota) * CHARS_PER_TOKEN_ESTIMATE)


@dataclass(frozen=True)
class CompletionQuotas:
    """
    Fixed percentage slices of one LLM completion request budget.

    Manage ratios via env (see ``.env.example`` § Completion quotas). Values here are
    always derived from ``context_window_tokens`` — never operator-fixed token counts.
    """

    context_window_tokens: int
    source: str
    soft_limit_tokens: int
    hard_limit_tokens: int
    tools_budget_tokens: int
    max_tool_count: int
    message_max_chars: int
    tool_result_max_chars: int
    compaction_input_max_chars: int

    @property
    def soft_ratio(self) -> float:
        w = self.context_window_tokens
        return self.soft_limit_tokens / w if w > 0 else 0.0

    @property
    def hard_ratio(self) -> float:
        w = self.context_window_tokens
        return self.hard_limit_tokens / w if w > 0 else 0.0

    @property
    def tools_budget_ratio(self) -> float:
        w = self.context_window_tokens
        return self.tools_budget_tokens / w if w > 0 else 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "context_window_tokens": self.context_window_tokens,
            "source": self.source,
            "soft_limit_tokens": self.soft_limit_tokens,
            "hard_limit_tokens": self.hard_limit_tokens,
            "tools_budget_tokens": self.tools_budget_tokens,
            "max_tool_count": self.max_tool_count,
            "message_max_chars": self.message_max_chars,
            "tool_result_max_chars": self.tool_result_max_chars,
            "compaction_input_max_chars": self.compaction_input_max_chars,
            "soft_ratio": round(self.soft_ratio, 6),
            "hard_ratio": round(self.hard_ratio, 6),
            "tools_budget_ratio": round(self.tools_budget_ratio, 6),
        }


def completion_quotas_from_window(
    context_window_tokens: int,
    *,
    source: str,
    tenant_id: int | None = None,
) -> CompletionQuotas:
    """Derive all per-completion slices from provider context window × configured ratios."""
    from apps.backend.infrastructure.agent_runtime import agent_config_effective as ace

    tid = tenant_id
    if tid is None:
        try:
            from apps.backend.domain.shared.identity import get_identity

            raw_tid, _uid = get_identity()
            tid = int(raw_tid) if raw_tid is not None else None
        except Exception:
            tid = None

    budget = limits_from_context_window(context_window_tokens, source=source)
    window = budget.context_window_tokens
    tools_ratio = ace.context_tools_budget_ratio(tenant_id=tid)
    tool_res_ratio = ace.context_tool_result_max_ratio(tenant_id=tid)
    tools_tok = _quota_tokens(window, tools_ratio)
    msg_tok = _quota_tokens(window, config.CHAT_CONTEXT_MAX_MESSAGE_RATIO)
    tool_res_tok = _quota_tokens(window, tool_res_ratio)
    compact_tok = _quota_tokens(window, config.CHAT_CONTEXT_COMPACTION_INPUT_RATIO)
    max_tools = max(1, int(window * config.AGENT_TOOLS_COUNT_CAP_RATIO))
    return CompletionQuotas(
        context_window_tokens=window,
        source=source,
        soft_limit_tokens=budget.soft_limit_tokens,
        hard_limit_tokens=budget.hard_limit_tokens,
        tools_budget_tokens=tools_tok,
        max_tool_count=max_tools,
        message_max_chars=_quota_chars_from_tokens(msg_tok),
        tool_result_max_chars=_quota_chars_from_tokens(tool_res_tok),
        compaction_input_max_chars=_quota_chars_from_tokens(compact_tok),
    )


def completion_quotas_from_budget(
    budget: ContextBudget,
    *,
    tenant_id: int | None = None,
) -> CompletionQuotas:
    return completion_quotas_from_window(
        budget.context_window_tokens,
        source=budget.source,
        tenant_id=tenant_id,
    )


def resolve_completion_quotas(
    model_id: str | None,
    *,
    catalog_owned_by: str | None = None,
) -> CompletionQuotas | None:
    """Provider window → all completion quotas (None when context window unknown)."""
    budget = resolve_context_budget(model_id, catalog_owned_by=catalog_owned_by)
    if budget is None:
        return None
    return completion_quotas_from_budget(budget)


def message_max_chars_for_budget(context_budget: ContextBudget | None) -> int | None:
    if context_budget is None:
        return None
    return completion_quotas_from_budget(context_budget).message_max_chars


def tool_result_max_chars_for_budget(context_budget: ContextBudget | None) -> int | None:
    if context_budget is None:
        return None
    return completion_quotas_from_budget(context_budget).tool_result_max_chars


def compaction_input_max_chars_for_budget(context_budget: ContextBudget | None) -> int | None:
    if context_budget is None:
        return None
    return completion_quotas_from_budget(context_budget).compaction_input_max_chars


def limits_from_context_window(context_window_tokens: int, *, source: str) -> ContextBudget:
    window = max(1, int(context_window_tokens))
    soft = _quota_tokens(window, config.CHAT_CONTEXT_SOFT_LIMIT_RATIO)
    hard = max(soft, _quota_tokens(window, config.CHAT_CONTEXT_HARD_LIMIT_RATIO))
    return ContextBudget(
        context_window_tokens=window,
        soft_limit_tokens=soft,
        hard_limit_tokens=hard,
        source=source,
    )


def resolve_context_budget(
    model_id: str | None,
    *,
    catalog_owned_by: str | None = None,
) -> ContextBudget | None:
    """
    Resolve model context window for percentage-based limits.

    Priority: operator per-model override → provider catalog metadata → optional
    ``CHAT_CONTEXT_DEFAULT_BUDGET_TOKENS`` when explicitly set (>0).
    """
    mid = (model_id or "").strip()
    overrides = _model_budget_overrides()
    if mid and mid in overrides:
        return limits_from_context_window(overrides[mid], source="operator_override")

    if mid and catalog_owned_by:
        from apps.backend.infrastructure.providers.model_catalog_providers import lookup_model_context_length

        provider_n = lookup_model_context_length(mid, catalog_owned_by)
        if provider_n:
            return limits_from_context_window(provider_n, source="provider_catalog")

    fallback = int(getattr(config, "CHAT_CONTEXT_DEFAULT_BUDGET_TOKENS", 0) or 0)
    if fallback > 0:
        return limits_from_context_window(fallback, source="operator_fallback")
    return None


def usage_prompt_tokens(usage: dict[str, Any] | None) -> int | None:
    if not isinstance(usage, dict):
        return None
    for key in ("prompt_tokens", "prompt"):
        n = _positive_int(usage.get(key))
        if n is not None:
            return n
    return None


def should_compact_by_usage(
    budget: ContextBudget | None,
    provider_prompt_tokens: int | None,
) -> tuple[bool, bool]:
    """Return (at_soft, at_hard) from provider-reported prompt token count."""
    if budget is None or provider_prompt_tokens is None or provider_prompt_tokens <= 0:
        return False, False
    at_soft = provider_prompt_tokens >= budget.soft_limit_tokens
    at_hard = provider_prompt_tokens >= budget.hard_limit_tokens
    return at_soft, at_hard
