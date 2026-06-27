"""Provider value objects."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

ProviderKind = Literal["llm", "embedding", "voice", "extractor"]

_PROVIDER_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


@dataclass(frozen=True, slots=True)
class ProviderId:
    value: str

    @classmethod
    def parse(cls, raw: str) -> "ProviderId":
        value = (raw or "").strip().lower()
        if not _PROVIDER_ID_RE.match(value):
            raise ValueError("provider id must be lowercase slug text")
        return cls(value)

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class ProviderLabel:
    value: str

    @classmethod
    def parse(cls, raw: str | None) -> "ProviderLabel":
        value = (raw or "").strip()
        if not value:
            raise ValueError("provider label is required")
        if len(value) > 200:
            raise ValueError("provider label must be <= 200 characters")
        return cls(value)

    def __str__(self) -> str:
        return self.value


def normalize_provider_kind(raw: str) -> ProviderKind:
    kind = (raw or "").strip().lower()
    if kind not in ("llm", "embedding", "voice", "extractor"):
        raise ValueError("provider kind must be llm, embedding, voice, or extractor")
    return kind  # type: ignore[return-value]
