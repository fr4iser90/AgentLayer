"""Setup entities."""
from __future__ import annotations

from dataclasses import dataclass, field

from apps.backend.domain.setup.value_objects import SetupProfileName, SetupStepKey


@dataclass(slots=True)
class SetupStep:
    key: SetupStepKey
    title: str
    completed: bool = False

    def __post_init__(self) -> None:
        if not self.title.strip():
            raise ValueError("setup step title must not be blank")


@dataclass(slots=True)
class SetupProfile:
    name: SetupProfileName
    steps: list[SetupStep] = field(default_factory=list)

    def completion_ratio(self) -> float:
        if not self.steps:
            return 1.0
        return sum(1 for step in self.steps if step.completed) / len(self.steps)
