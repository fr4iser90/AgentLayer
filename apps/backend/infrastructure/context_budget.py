"""Context window resolution (provider metadata) and usage-based budget limits."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from apps.backend.core.config import config

logger = logging.getLogger(__name__)

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


def limits_from_context_window(context_window_tokens: int, *, source: str) -> ContextBudget:
    window = max(1, int(context_window_tokens))
    soft = max(1, int(window * config.CHAT_CONTEXT_SOFT_LIMIT_RATIO))
    hard = max(soft, int(window * config.CHAT_CONTEXT_HARD_LIMIT_RATIO))
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
        from apps.backend.infrastructure.model_catalog_providers import lookup_model_context_length

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
