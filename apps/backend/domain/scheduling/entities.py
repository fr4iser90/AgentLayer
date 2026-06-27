"""Scheduling entities."""
from __future__ import annotations

from dataclasses import dataclass

from apps.backend.domain.scheduling.value_objects import CronExpression, ScheduleId


@dataclass(slots=True)
class ScheduledJob:
    id: ScheduleId
    name: str
    cron: CronExpression
    target: str
    enabled: bool = True

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("scheduled job name must not be blank")
        if not self.target.strip():
            raise ValueError("scheduled job target must not be blank")

    def disable(self) -> None:
        self.enabled = False
