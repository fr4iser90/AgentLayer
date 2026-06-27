"""Infrastructure adapter for chat audio attachment media ingest."""

from __future__ import annotations

import uuid
from typing import Any

from apps.backend.dashboard import file_storage
from apps.backend.domain import chat_audio_attachments as domain
from apps.backend.media import media_db, media_policy
from apps.backend.media.upload_bytes import sniff_media_mime


class _ChatAudioAttachmentDeps:
    media_tables_exist = staticmethod(media_db.media_tables_exist)
    effective_media_library_enabled = staticmethod(media_policy.effective_media_library_enabled)
    effective_media_upload_enabled = staticmethod(media_policy.effective_media_upload_enabled)
    effective_media_upload_max_bytes = staticmethod(media_policy.effective_media_upload_max_bytes)
    effective_media_upload_mime = staticmethod(media_policy.effective_media_upload_mime)
    sniff_media_mime = staticmethod(sniff_media_mime)
    user_upload_bytes_used = staticmethod(media_db.user_upload_bytes_used)
    effective_media_quota_bytes = staticmethod(media_policy.effective_media_quota_bytes)
    write_bytes = staticmethod(file_storage.write_bytes)
    unlink_if_exists = staticmethod(file_storage.unlink_if_exists)

    @staticmethod
    def item_insert_upload(**kwargs: Any) -> dict[str, Any]:
        return media_db.item_insert_upload(**kwargs)


domain.register_chat_audio_attachment_dependencies(_ChatAudioAttachmentDeps())

format_ingested_audio_system_block = domain.format_ingested_audio_system_block
ingest_chat_audio_attachments = domain.ingest_chat_audio_attachments
triggering_user_message = domain.triggering_user_message
