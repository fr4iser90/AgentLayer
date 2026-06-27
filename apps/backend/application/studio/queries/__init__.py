"""Studio read queries."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class GetStudioJobQuery:
    job_id: str


@dataclass(frozen=True, slots=True)
class ListStudioJobsQuery:
    status: str | None = None
