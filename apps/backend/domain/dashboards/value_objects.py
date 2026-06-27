"""Dashboard value objects and invariants."""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from typing import Literal

DashboardRole = Literal["owner", "co_owner", "editor", "viewer"]

_KIND_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


@dataclass(frozen=True, slots=True)
class DashboardId:
    value: uuid.UUID

    @classmethod
    def parse(cls, raw: str | uuid.UUID) -> "DashboardId":
        return cls(raw if isinstance(raw, uuid.UUID) else uuid.UUID(str(raw)))

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True, slots=True)
class DashboardKind:
    value: str

    @classmethod
    def parse(cls, raw: str | None) -> "DashboardKind":
        value = (raw or "custom").strip().lower()
        if not _KIND_RE.match(value):
            raise ValueError("dashboard kind must be lowercase slug text")
        return cls(value)

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class DashboardTitle:
    value: str

    @classmethod
    def parse(cls, raw: str | None) -> "DashboardTitle":
        value = (raw or "").strip() or "Dashboard"
        if len(value) > 500:
            raise ValueError("dashboard title must be <= 500 characters")
        return cls(value)

    def __str__(self) -> str:
        return self.value
