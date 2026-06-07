"""Shared bridge → chat_completion → persist turn (Telegram, Discord, voice)."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from apps.backend.domain.agent import chat_completion
from apps.backend.domain.identity import reset_identity, set_identity
from apps.backend.infrastructure.conversations_db import conversation_append_message
from apps.backend.infrastructure.db import db
from apps.backend.infrastructure.bridge_agent_session import (
    MAX_CONTEXT_MESSAGES,
    bridge_agent_conversation_ensure,
    bridge_chat_completion_extras,
    bridge_try_slash_command,
    messages_for_bridge_completion,
)

logger = logging.getLogger(__name__)


def extract_bridge_reply(data: dict[str, Any]) -> str:
    err = data.get("error") or data.get("detail")
    if isinstance(err, dict):
        err = err.get("message") or str(err)
    if err and not data.get("choices"):
        return f"AgentLayer error: {err}"
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        return f"Unexpected response: {data!r:.2000}"
    msg = choices[0].get("message") or {}
    content = msg.get("content")
    if isinstance(content, str) and content.strip():
        return content.strip()
    return "(empty reply)"


async def run_bridge_agent_turn(
    *,
    user_id: uuid.UUID,
    tenant_id: int,
    prompt: str,
    model: str,
    catalog_owned_by: str,
    provider: str,
    scope_chat_id: int,
    scope_thread_id: int | None,
) -> tuple[str, uuid.UUID]:
    """
    Run one agent turn for an external bridge channel.
    Returns (assistant_reply, conversation_id).
    """
    text = (prompt or "").strip()
    if not text:
        raise ValueError("empty prompt")

    conv_id = bridge_agent_conversation_ensure(
        user_id,
        tenant_id,
        provider=provider,
        scope_chat_id=scope_chat_id,
        scope_thread_id=scope_thread_id,
        model=model,
    )
    slash_reply = bridge_try_slash_command(
        text,
        user_id=user_id,
        provider=provider,
        scope_chat_id=scope_chat_id,
        scope_thread_id=scope_thread_id,
    )
    if slash_reply is not None:
        return slash_reply.strip(), conv_id

    msg_list = messages_for_bridge_completion(user_id, conv_id, new_user_text=text)
    logger.debug(
        "bridge_agent_turn: conversation_id=%s ctx_messages=%d (cap=%d)",
        conv_id,
        len(msg_list),
        MAX_CONTEXT_MESSAGES + 1,
    )
    work: dict[str, Any] = {
        "model": model,
        "agent_model_catalog_owned_by": catalog_owned_by,
        "messages": msg_list,
        "stream": False,
        "conversation_id": str(conv_id),
    }
    work.update(
        bridge_chat_completion_extras(
            user_id,
            provider=provider,
            scope_chat_id=scope_chat_id,
            scope_thread_id=scope_thread_id,
        )
    )
    role = db.user_role(user_id).lower()
    bearer_role = role if role in ("user", "admin") else None
    id_token = set_identity(tenant_id, user_id)
    try:
        result = await chat_completion(work, bearer_user_role=bearer_role)
        reply = extract_bridge_reply(result if isinstance(result, dict) else {})
        if not conversation_append_message(user_id, conv_id, role="user", content=text) or not conversation_append_message(
            user_id, conv_id, role="assistant", content=reply
        ):
            logger.warning("bridge_agent_turn: failed to persist turn (conversation_id=%s)", conv_id)
        return reply, conv_id
    finally:
        reset_identity(id_token)
