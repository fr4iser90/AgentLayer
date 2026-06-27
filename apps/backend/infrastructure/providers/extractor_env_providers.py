"""Parse numbered ``EXTRACTOR_PROVIDER_N_*`` env rows."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any

_ENV_PREFIX = "EXTRACTOR_PROVIDER_"
_ENV_INDEX_RE = re.compile(r"^EXTRACTOR_PROVIDER_(\d+)_BASE_URL$")


def strip_env_value(raw: str | None) -> str:
    s = (raw or "").strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in ('"', "'"):
        s = s[1:-1].strip()
    return s


def strip_opt(raw: Any) -> str | None:
    if raw is None:
        return None
    s = str(raw).strip()
    return s or None


@dataclass(frozen=True)
class EnvExtractorProviderRow:
    index: int
    provider_id: str
    label: str
    base_url: str
    api_key: str
    api_header_name: str
    model_default: str | None = None
    timeout_sec: float = 120.0
    source: str = "env"


def env_extractor_provider_id(index: int) -> str:
    name = strip_env_value(os.environ.get(f"{_ENV_PREFIX}{index}_NAME"))
    if name:
        pid = "".join(c for c in name.strip().lower() if c.isalnum() or c in "_-")[:64]
        if pid:
            return pid
    return f"extractor_provider_{int(index)}"


def _configured_env_indexes() -> list[int]:
    indexes: set[int] = set()
    for key, value in os.environ.items():
        m = _ENV_INDEX_RE.match(key)
        if not m or not strip_env_value(value):
            continue
        try:
            indexes.add(int(m.group(1)))
        except ValueError:
            continue
    return sorted(indexes)


def _float_env(name: str, default: float) -> float:
    try:
        return float(strip_env_value(os.environ.get(name)) or default)
    except (TypeError, ValueError):
        return default


def _read_numbered_env_row(n: int) -> EnvExtractorProviderRow | None:
    base = strip_env_value(os.environ.get(f"{_ENV_PREFIX}{n}_BASE_URL")).rstrip("/")
    if not base:
        return None
    name = strip_env_value(os.environ.get(f"{_ENV_PREFIX}{n}_NAME"))
    label = strip_env_value(os.environ.get(f"{_ENV_PREFIX}{n}_LABEL")) or name or f"Extractor {n}"
    return EnvExtractorProviderRow(
        index=n,
        provider_id=env_extractor_provider_id(n),
        label=label[:128],
        base_url=base,
        api_key=strip_env_value(os.environ.get(f"{_ENV_PREFIX}{n}_API_KEY")),
        api_header_name=strip_env_value(os.environ.get(f"{_ENV_PREFIX}{n}_API_HEADER_NAME")) or "X-API-KEY",
        model_default=strip_opt(os.environ.get(f"{_ENV_PREFIX}{n}_MODEL")),
        timeout_sec=max(1.0, min(_float_env(f"{_ENV_PREFIX}{n}_TIMEOUT_SEC", 120.0), 1800.0)),
        source="env",
    )


def parse_extractor_env_providers() -> list[EnvExtractorProviderRow]:
    rows: list[EnvExtractorProviderRow] = []
    for n in _configured_env_indexes():
        row = _read_numbered_env_row(n)
        if row is not None:
            rows.append(row)
    return rows

