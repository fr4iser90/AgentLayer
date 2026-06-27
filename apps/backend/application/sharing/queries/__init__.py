"""Sharing read queries."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class GetShareGrantQuery:
    share_id: str


@dataclass(frozen=True, slots=True)
class ListShareGrantsQuery:
    resource_kind: str
    resource_id: str
