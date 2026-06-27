"""Sharing write commands."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SaveShareGrantCommand:
    share_id: str
    resource_kind: str
    resource_id: str
    grantee: str
    role: str
    revoked: bool = False
