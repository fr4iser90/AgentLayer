"""Setup DTOs."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SetupStepDto:
    key: str
    title: str
    completed: bool


@dataclass(frozen=True, slots=True)
class SetupProfileDto:
    name: str
    steps: list[SetupStepDto]
    completion_ratio: float
