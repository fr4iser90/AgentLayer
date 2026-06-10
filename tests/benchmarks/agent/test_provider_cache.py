"""Provider prompt-cache policy for benchmarks."""

from __future__ import annotations

import os

from tests.benchmarks.agent.metrics import live_snapshot_from_ws_events, usage_cached_prompt_tokens
from tests.benchmarks.agent.provider_cache import (
    apply_bench_provider_cache_policy,
    bench_disable_provider_prompt_cache,
)


def test_bench_disable_provider_prompt_cache_default_off(monkeypatch) -> None:
    monkeypatch.delenv("AGENT_BENCH_DISABLE_PROVIDER_PROMPT_CACHE", raising=False)
    assert bench_disable_provider_prompt_cache() is False


def test_apply_bench_provider_cache_policy_default_leaves_body(monkeypatch) -> None:
    monkeypatch.delenv("AGENT_BENCH_DISABLE_PROVIDER_PROMPT_CACHE", raising=False)
    body: dict = {"messages": [{"role": "user", "content": "hi"}]}
    apply_bench_provider_cache_policy(body)
    assert "cache_prompt" not in body


def test_apply_bench_provider_cache_policy_opt_in(monkeypatch) -> None:
    monkeypatch.setenv("AGENT_BENCH_DISABLE_PROVIDER_PROMPT_CACHE", "1")
    body: dict = {"messages": []}
    apply_bench_provider_cache_policy(body)
    assert body["cache_prompt"] is False


def test_usage_cached_prompt_tokens_openai_details() -> None:
    n = usage_cached_prompt_tokens(
        {"prompt_tokens": 5000, "prompt_tokens_details": {"cached_tokens": 4200}}
    )
    assert n == 4200


def test_live_snapshot_includes_provider_prompt_tokens() -> None:
    events = [
        {
            "type": "agent.context_update",
            "context": {"provider_prompt_tokens": 4054, "context_window_tokens": 65536},
        },
        {"type": "agent.llm_round_start", "round": 1},
    ]
    snap = live_snapshot_from_ws_events(events, elapsed_ms=100.0)
    assert snap["provider_prompt_tokens"] == 4054
    assert snap["context_window_tokens"] == 65536
