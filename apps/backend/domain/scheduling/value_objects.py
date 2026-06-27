"""Scheduling value objects."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ScheduleId:
    value: str

    @classmethod
    def parse(cls, raw: str) -> "ScheduleId":
        value = raw.strip()
        if not value:
            raise ValueError("schedule id must not be blank")
        return cls(value)


@dataclass(frozen=True, slots=True)
class CronExpression:
    value: str

    @classmethod
    def parse(cls, raw: str) -> "CronExpression":
        value = raw.strip()
        if len(value.split()) != 5:
            raise ValueError("cron expression must contain five fields")
        return cls(value)
