"""Repository ports for studio jobs."""
from __future__ import annotations

from typing import Protocol

from apps.backend.domain.studio.entities import StudioJob
from apps.backend.domain.studio.value_objects import StudioJobId


class StudioJobRepository(Protocol):
    def get(self, job_id: StudioJobId) -> StudioJob | None: ...

    def list_by_status(self, status: str | None = None) -> list[StudioJob]: ...

    def save(self, job: StudioJob) -> StudioJob: ...
