"""Sharing value objects."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ShareId:
    value: str

    @classmethod
    def parse(cls, raw: str) -> "ShareId":
        value = raw.strip()
        if not value:
            raise ValueError("share id must not be blank")
        return cls(value)


@dataclass(frozen=True, slots=True)
class ShareResource:
    kind: str
    resource_id: str

    def __post_init__(self) -> None:
        if not self.kind.strip():
            raise ValueError("share resource kind must not be blank")
        if not self.resource_id.strip():
            raise ValueError("share resource id must not be blank")
