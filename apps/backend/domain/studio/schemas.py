"""Studio schema validation."""
from __future__ import annotations

from collections.abc import Mapping


def validate_studio_job_status(status: str) -> str:
    value = status.strip().lower()
    if value not in {"queued", "running", "succeeded", "failed", "cancelled"}:
        raise ValueError("invalid studio job status")
    return value


def validate_studio_payload(payload: Mapping[str, object] | None) -> dict[str, object]:
    return dict(payload or {})
