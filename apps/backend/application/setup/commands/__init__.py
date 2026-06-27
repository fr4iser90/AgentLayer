"""Setup write commands."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SetupStepInput:
    key: str
    title: str
    completed: bool = False


@dataclass(frozen=True, slots=True)
class SaveSetupProfileCommand:
    name: str
    steps: list[SetupStepInput]
