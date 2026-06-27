"""Plugin system value objects."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PluginId:
    value: str

    @classmethod
    def parse(cls, raw: str) -> "PluginId":
        value = raw.strip()
        if not value:
            raise ValueError("plugin id must not be blank")
        if any(char.isspace() for char in value):
            raise ValueError("plugin id must not contain whitespace")
        return cls(value)
