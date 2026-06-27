"""Repository ports for shares."""
from __future__ import annotations

from typing import Protocol

from apps.backend.domain.shares.entities import ShareGrant
from apps.backend.domain.shares.value_objects import ShareId, ShareResource


class ShareGrantRepository(Protocol):
    def get(self, share_id: ShareId) -> ShareGrant | None: ...

    def list_for_resource(self, resource: ShareResource) -> list[ShareGrant]: ...

    def save(self, grant: ShareGrant) -> ShareGrant: ...
