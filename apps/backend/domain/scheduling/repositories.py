"""Repository ports for scheduling."""
from __future__ import annotations

from typing import Protocol

from apps.backend.domain.scheduling.entities import ScheduledJob
from apps.backend.domain.scheduling.value_objects import ScheduleId


class ScheduledJobRepository(Protocol):
    def get(self, schedule_id: ScheduleId) -> ScheduledJob | None: ...

    def list_enabled(self) -> list[ScheduledJob]: ...

    def save(self, job: ScheduledJob) -> ScheduledJob: ...
