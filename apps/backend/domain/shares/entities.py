"""Sharing entities."""
from __future__ import annotations

from dataclasses import dataclass

from apps.backend.domain.shares.value_objects import ShareId, ShareResource


@dataclass(slots=True)
class ShareGrant:
    id: ShareId
    resource: ShareResource
    grantee: str
    role: str
    revoked: bool = False

    def __post_init__(self) -> None:
        if not self.grantee.strip():
            raise ValueError("share grantee must not be blank")
        if self.role not in {"viewer", "editor", "owner"}:
            raise ValueError("share role must be viewer, editor, or owner")

    def revoke(self) -> None:
        self.revoked = True
