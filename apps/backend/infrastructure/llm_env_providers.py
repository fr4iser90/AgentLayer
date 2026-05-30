"""Parse numbered ``LLM_PROVIDER_N_*`` env rows."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

LLM_ENV_PROVIDER_MAX = 32
_ENV_PREFIX = "LLM_PROVIDER_"


def strip_env_value(raw: str | None) -> str:
    s = (raw or "").strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in ('"', "'"):
        s = s[1:-1].strip()
    return s


def strip_opt(s: Any) -> str | None:
    if s is None:
        return None
    t = str(s).strip()
    return t or None


@dataclass(frozen=True)
class EnvLlmProviderRow:
    index: int
    provider_id: str
    label: str
    base_url: str
    api_key: str
    api_header_name: str
    model_default: str | None = None
    model_vlm: str | None = None
    model_agent: str | None = None
    model_coding: str | None = None
    source: str = "env"


def env_provider_id(index: int) -> str:
    return f"provider_{int(index)}"


def _read_numbered_env_row(n: int) -> EnvLlmProviderRow | None:
    base = strip_env_value(os.environ.get(f"{_ENV_PREFIX}{n}_BASE_URL")).rstrip("/")
    if not base:
        return None
    label = strip_env_value(os.environ.get(f"{_ENV_PREFIX}{n}_LABEL")) or f"Provider {n}"
    api_key = strip_env_value(os.environ.get(f"{_ENV_PREFIX}{n}_API_KEY"))
    header = (
        strip_env_value(os.environ.get(f"{_ENV_PREFIX}{n}_API_HEADER_NAME")) or "Authorization"
    )
    return EnvLlmProviderRow(
        index=n,
        provider_id=env_provider_id(n),
        label=label[:128],
        base_url=base,
        api_key=api_key,
        api_header_name=header[:128],
        model_default=strip_opt(os.environ.get(f"{_ENV_PREFIX}{n}_MODEL_DEFAULT")),
        model_vlm=strip_opt(os.environ.get(f"{_ENV_PREFIX}{n}_MODEL_VLM")),
        model_agent=strip_opt(os.environ.get(f"{_ENV_PREFIX}{n}_MODEL_AGENT")),
        model_coding=strip_opt(os.environ.get(f"{_ENV_PREFIX}{n}_MODEL_CODING")),
        source="env",
    )


def parse_llm_env_providers() -> list[EnvLlmProviderRow]:
    rows: list[EnvLlmProviderRow] = []
    for n in range(1, LLM_ENV_PROVIDER_MAX + 1):
        row = _read_numbered_env_row(n)
        if row is not None:
            rows.append(row)
    return rows
