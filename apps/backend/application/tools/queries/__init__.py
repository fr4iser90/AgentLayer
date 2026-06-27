"""Tool system read queries."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class GetToolDefinitionQuery:
    name: str


@dataclass(frozen=True, slots=True)
class ListToolDefinitionsQuery:
    namespace: str | None = None
