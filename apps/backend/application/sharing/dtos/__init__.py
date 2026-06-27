"""Sharing DTOs."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ShareGrantDto:
    share_id: str
    resource_kind: str
    resource_id: str
    grantee: str
    role: str
    revoked: bool
