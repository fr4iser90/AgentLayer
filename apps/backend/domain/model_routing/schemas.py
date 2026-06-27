"""Model routing schema validation."""
from __future__ import annotations


def validate_routing_priority(priority: object) -> int:
    if not isinstance(priority, int):
        raise ValueError("routing priority must be an integer")
    if priority < 0:
        raise ValueError("routing priority must be non-negative")
    return priority


def validate_routing_provider(provider: str) -> str:
    value = provider.strip()
    if not value:
        raise ValueError("routing provider must not be blank")
    return value
