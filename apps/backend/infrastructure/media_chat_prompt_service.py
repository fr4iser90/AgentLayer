"""Infrastructure adapter for media library chat prompt context."""

from __future__ import annotations

import uuid
from typing import Any

from apps.backend.dashboard import db as dashboard_db
from apps.backend.domain import media_chat_prompt as domain
from apps.backend.media import media_db, media_policy


class _MediaChatPromptDeps:
    media_tables_exist = staticmethod(media_db.media_tables_exist)
    effective_media_library_enabled = staticmethod(media_policy.effective_media_library_enabled)
    media_quota_snapshot = staticmethod(media_policy.media_quota_snapshot)

    @staticmethod
    def dashboard_list(
        user_id: uuid.UUID,
        tenant_id: int,
        *,
        limit: int = 40,
    ) -> list[dict[str, Any]]:
        return dashboard_db.dashboard_list(user_id, tenant_id, limit=limit)


domain.register_media_chat_prompt_dependencies(_MediaChatPromptDeps())

build_media_library_context_snippet = domain.build_media_library_context_snippet
