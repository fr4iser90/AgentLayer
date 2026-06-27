"""Model routing read queries."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ListModelRoutesQuery:
    profile: str
