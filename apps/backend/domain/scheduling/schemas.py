"""Scheduling schema validation."""
from __future__ import annotations


def validate_cron_expression(expression: str) -> str:
    value = expression.strip()
    if len(value.split()) != 5:
        raise ValueError("cron expression must contain five fields")
    return value


def validate_schedule_target(target: str) -> str:
    value = target.strip()
    if not value:
        raise ValueError("schedule target must not be blank")
    return value
