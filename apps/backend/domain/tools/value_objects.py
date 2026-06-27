"""Tool value objects."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ToolName:
    value: str

    @classmethod
    def parse(cls, raw: str) -> "ToolName":
        value = raw.strip()
        if not value:
            raise ValueError("tool name must not be blank")
        if any(char.isspace() for char in value):
            raise ValueError("tool name must not contain whitespace")
        return cls(value)


@dataclass(frozen=True, slots=True)
class ToolNamespace:
    value: str

    @classmethod
    def parse(cls, raw: str) -> "ToolNamespace":
        value = raw.strip()
        if not value:
            raise ValueError("tool namespace must not be blank")
        return cls(value)
