"""Model routing write commands."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SaveModelRouteCommand:
    profile: str
    model_id: str
    provider: str
    priority: int = 100
