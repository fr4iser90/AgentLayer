"""Value objects for collection-backed dashboard data."""

from __future__ import annotations

import re
from dataclasses import dataclass

_SLUG_RE = re.compile(r"^[a-z][a-z0-9._-]{0,95}$")
FILE_REF_PREFIX = "file:"


@dataclass(frozen=True, slots=True)
class CollectionSlug:
    value: str

    @classmethod
    def parse(cls, raw: str) -> "CollectionSlug | None":
        value = (raw or "").strip().lower()
        if not value or not _SLUG_RE.match(value):
            return None
        return cls(value)

    @classmethod
    def require(cls, raw: str) -> "CollectionSlug":
        parsed = cls.parse(raw)
        if parsed is None:
            raise ValueError("invalid collection slug")
        return parsed

    @classmethod
    def for_data_path(cls, data_path: str) -> "CollectionSlug":
        value = (data_path or "").strip()
        return cls.require((value or "items").replace(" ", "_").lower())

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class DataPath:
    value: str

    @classmethod
    def parse(cls, raw: str) -> "DataPath | None":
        value = (raw or "").strip()
        if not value:
            return None
        return cls(value)

    def top_level_key(self) -> str:
        return self.value.split(".", 1)[0]

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class FileRef:
    file_id: str

    @classmethod
    def parse(cls, raw: str) -> "FileRef | None":
        value = (raw or "").strip()
        if not value.startswith(FILE_REF_PREFIX):
            return None
        file_id = value[len(FILE_REF_PREFIX) :].strip()
        return cls(file_id) if file_id else None

    def __str__(self) -> str:
        return f"{FILE_REF_PREFIX}{self.file_id}"
