"""Setup schema validation."""
from __future__ import annotations


def validate_setup_step_title(title: str) -> str:
    value = title.strip()
    if not value:
        raise ValueError("setup step title must not be blank")
    if len(value) > 200:
        raise ValueError("setup step title is too long")
    return value


def validate_setup_completed(completed: object) -> bool:
    if not isinstance(completed, bool):
        raise ValueError("setup completion flag must be boolean")
    return completed
