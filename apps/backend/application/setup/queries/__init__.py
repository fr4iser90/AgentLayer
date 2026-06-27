"""Setup read queries."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class GetSetupProfileQuery:
    name: str


@dataclass(frozen=True, slots=True)
class ListSetupProfilesQuery:
    pass
