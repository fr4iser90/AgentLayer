"""Provider-side prompt/KV cache policy for agent benchmarks.

AgentLayer does not implement LLM KV cache — only the upstream server (e.g. llama.cpp
``cache_prompt``, OpenAI ``cached_tokens``) does. Benchmarks disable cross-scenario reuse
by default so each scenario measures full prompt work unless opted out.
"""

from __future__ import annotations

import os
from typing import Any


def bench_disable_provider_prompt_cache() -> bool:
    """When true, benchmark chat bodies set ``cache_prompt: false`` (llama.cpp / compat)."""
    raw = (os.environ.get("AGENT_BENCH_DISABLE_PROVIDER_PROMPT_CACHE") or "0").strip().lower()
    return raw in ("1", "true", "yes", "on")


def apply_bench_provider_cache_policy(body: dict[str, Any]) -> dict[str, Any]:
    if bench_disable_provider_prompt_cache():
        body["cache_prompt"] = False
    return body
