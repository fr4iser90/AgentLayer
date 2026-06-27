from __future__ import annotations

import uuid
from typing import Any

from apps.backend.infrastructure.db import db
from apps.backend.infrastructure.notifications import message_feedback_store
from apps.backend.infrastructure.platform.conversations_db import conversation_get


def get_conversation_for_feedback(user_id: uuid.UUID, conversation_id: uuid.UUID) -> dict[str, Any] | None:
    return conversation_get(user_id, conversation_id)


def upsert_feedback_for_message(
    *,
    user_id: uuid.UUID,
    conversation_id: uuid.UUID,
    message_position: int,
    rating: int,
    comment: str | None,
) -> dict[str, Any]:
    return message_feedback_store.upsert_feedback(
        tenant_id=db.user_tenant_id(user_id),
        user_id=user_id,
        conversation_id=conversation_id,
        message_position=message_position,
        rating=rating,
        comment=comment,
    )


def list_feedback_for_conversation(
    *,
    user_id: uuid.UUID,
    conversation_id: uuid.UUID,
) -> list[dict[str, Any]]:
    return message_feedback_store.list_feedback_for_conversation(
        user_id=user_id,
        conversation_id=conversation_id,
    )


def list_feedback_for_admin(*, admin_user_id: uuid.UUID, limit: int) -> list[dict[str, Any]]:
    return message_feedback_store.list_feedback_admin(
        tenant_id=db.user_tenant_id(admin_user_id),
        limit=limit,
    )
