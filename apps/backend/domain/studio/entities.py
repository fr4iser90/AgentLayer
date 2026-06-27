"""Studio entities."""
from __future__ import annotations

from dataclasses import dataclass, field

from apps.backend.domain.studio.value_objects import StudioJobId, StudioJobKind


@dataclass(slots=True)
class StudioJob:
    id: StudioJobId
    kind: StudioJobKind
    status: str
    payload: dict[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.status not in {"queued", "running", "succeeded", "failed", "cancelled"}:
            raise ValueError("invalid studio job status")

    def mark_failed(self) -> None:
        self.status = "failed"
