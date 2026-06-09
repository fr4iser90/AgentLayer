"""Benchmark LLM profiles from ``AGENT_BENCH_LLM_*`` in ``.env`` (CLI fallback)."""

from __future__ import annotations

import os
from dataclasses import dataclass

_BENCH_LLM_PREFIX = "AGENT_BENCH_LLM_"
_BENCH_LLM_MAX = 16


@dataclass(frozen=True)
class BenchModelProfile:
    label: str
    catalog_owned_by: str
    model: str
    agent_id: str = "general"
    base_url: str = ""
    api_key: str = ""
    api_header_name: str = ""
    slot: int = 0


def _strip(raw: str | None) -> str:
    return (raw or "").strip()


def parse_profiles_from_env() -> list[BenchModelProfile]:
    """
    Bench provider matrix in ``.env`` (``AGENT_BENCH_LLM_N_*``), optional when using DB endpoints:

      AGENT_BENCH_LLM_1_LABEL=ollama-remote
      AGENT_BENCH_LLM_1_BASE_URL=http://192.168.1.50:11434
      AGENT_BENCH_LLM_1_MODEL=qwen2.5:3b
      AGENT_BENCH_LLM_1_API_KEY=your-key
      AGENT_BENCH_LLM_1_API_HEADER_NAME=X-API-KEY   # or Authorization

    Legacy (use existing server catalog slot instead of BASE_URL):

      AGENT_BENCH_LLM_1_CATALOG=provider_2
      AGENT_BENCH_LLM_1_MODEL=qwen2.5:3b
    """
    rows: list[BenchModelProfile] = []
    for n in range(1, _BENCH_LLM_MAX + 1):
        base_url = _strip(os.environ.get(f"{_BENCH_LLM_PREFIX}{n}_BASE_URL"))
        catalog = _strip(os.environ.get(f"{_BENCH_LLM_PREFIX}{n}_CATALOG"))
        model = _strip(os.environ.get(f"{_BENCH_LLM_PREFIX}{n}_MODEL"))
        if not base_url and not catalog:
            continue
        label = _strip(os.environ.get(f"{_BENCH_LLM_PREFIX}{n}_LABEL")) or f"bench-llm-{n}"
        agent_id = _strip(os.environ.get(f"{_BENCH_LLM_PREFIX}{n}_AGENT")) or "general"
        api_key = _strip(os.environ.get(f"{_BENCH_LLM_PREFIX}{n}_API_KEY")).strip('"').strip("'")
        api_header_name = _strip(os.environ.get(f"{_BENCH_LLM_PREFIX}{n}_API_HEADER_NAME"))
        rows.append(
            BenchModelProfile(
                label=label,
                catalog_owned_by=catalog,
                model=model,
                agent_id=agent_id,
                base_url=base_url,
                api_key=api_key,
                api_header_name=api_header_name,
                slot=n,
            )
        )
    return rows


def profile_by_env_slot(slot: int) -> BenchModelProfile | None:
    n = int(slot)
    if n < 1 or n > _BENCH_LLM_MAX:
        return None
    for row in parse_profiles_from_env():
        if row.slot == n:
            return row
    return None


def serialize_env_profiles_for_admin() -> list[dict[str, object]]:
    """Public metadata for Admin UI (no API keys)."""
    out: list[dict[str, object]] = []
    for row in parse_profiles_from_env():
        out.append(
            {
                "slot": row.slot,
                "label": row.label,
                "model": row.model,
                "agent_id": row.agent_id,
                "base_url": row.base_url,
                "catalog_owned_by": row.catalog_owned_by or None,
                "api_key_configured": bool(row.api_key),
                "api_header_name": row.api_header_name or None,
                "source": "env_bench",
            }
        )
    return out


def profile_labels_filter() -> list[str] | None:
    """AGENT_BENCH_PROFILES=ollama-small,llama-cpp — filter manifest labels only."""
    raw = _strip(os.environ.get("AGENT_BENCH_PROFILES"))
    if not raw:
        return None
    labels = [p.strip() for p in raw.split(",") if p.strip()]
    return labels or None
