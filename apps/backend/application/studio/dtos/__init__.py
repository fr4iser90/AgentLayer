"""Studio DTOs."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class StudioJobDto:
    job_id: str
    kind: str
    status: str
    payload: dict[str, object] = field(default_factory=dict)
