"""Model routing DTOs."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ModelRouteDto:
    profile: str
    model_id: str
    provider: str
    priority: int
