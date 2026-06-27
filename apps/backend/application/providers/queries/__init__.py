"""Provider queries."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ListProviderEndpointsQuery:
    kind: str | None = None


@dataclass(frozen=True, slots=True)
class ListModelCatalogPreferencesQuery:
    pass
