"""Identity value objects."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

UserRole = Literal["user", "admin"]

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@dataclass(frozen=True, slots=True)
class TenantId:
    value: int

    def __post_init__(self) -> None:
        if self.value <= 0:
            raise ValueError("tenant id must be positive")

    def __int__(self) -> int:
        return self.value


@dataclass(frozen=True, slots=True)
class EmailAddress:
    value: str

    @classmethod
    def parse(cls, raw: str) -> "EmailAddress":
        value = (raw or "").strip().lower()
        if not value or len(value) > 254 or not _EMAIL_RE.match(value):
            raise ValueError("invalid email address")
        return cls(value)

    def __str__(self) -> str:
        return self.value
