"""Parse numbered ``EMBEDDING_PROVIDER_N_*`` env rows."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

EMBEDDING_ENV_PROVIDER_MAX = 32
_ENV_PREFIX = "EMBEDDING_PROVIDER_"


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
class EnvEmbeddingProviderRow:
    index: int
    provider_id: str
    label: str
    base_url: str
    api_key: str
    api_header_name: str
    model_default: str | None = None
    source: str = "env"


def env_embedding_provider_id(index: int) -> str:
    return f"embedding_provider_{int(index)}"


def _read_numbered_env_row(n: int) -> EnvEmbeddingProviderRow | None:
    base = strip_env_value(os.environ.get(f"{_ENV_PREFIX}{n}_BASE_URL")).rstrip("/")
    if not base:
        return None
    label = strip_env_value(os.environ.get(f"{_ENV_PREFIX}{n}_LABEL")) or f"Embedding {n}"
    api_key = strip_env_value(os.environ.get(f"{_ENV_PREFIX}{n}_API_KEY"))
    header = (
        strip_env_value(os.environ.get(f"{_ENV_PREFIX}{n}_API_HEADER_NAME")) or "X-API-KEY"
    )
    return EnvEmbeddingProviderRow(
        index=n,
        provider_id=env_embedding_provider_id(n),
        label=label[:128],
        base_url=base,
        api_key=api_key,
        api_header_name=header[:128],
        model_default=strip_opt(os.environ.get(f"{_ENV_PREFIX}{n}_MODEL_DEFAULT")),
        source="env",
    )


def parse_embedding_env_providers() -> list[EnvEmbeddingProviderRow]:
    rows: list[EnvEmbeddingProviderRow] = []
    for n in range(1, EMBEDDING_ENV_PROVIDER_MAX + 1):
        row = _read_numbered_env_row(n)
        if row is not None:
            rows.append(row)
    return rows
