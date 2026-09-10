"""Cross-turn context-inject digests: what the model already saw, and what may be omitted now."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from apps.backend.infrastructure.platform.config import config

logger = logging.getLogger(__name__)

__all__ = [
    "apply_omit_stub_and_ledger",
    "inject_agent_key",
    "load_prior_inject_digests",
    "needs_full_reinject",
    "persist_inject_digests",
]


def inject_agent_key(agent_id: str | None) -> str:
    return (agent_id or "default").strip().lower() or "default"


def load_prior_inject_digests(
    user_id: Any,
    conversation_id: uuid.UUID | None,
    agent_key: str,
) -> dict[str, str]:
    """Digests of the omitable injects already sent for this agent, keyed by inject kind."""
    if conversation_id is None or not isinstance(user_id, uuid.UUID):
        return {}
    try:
        from apps.backend.infrastructure.agent_runtime.conversation_inject_digest_store import (
            get_inject_digests,
        )

        raw_prior = get_inject_digests(user_id, conversation_id).get(agent_key) or {}
        if isinstance(raw_prior, dict):
            return {str(k): str(v) for k, v in raw_prior.items() if str(k) and str(v)}
    except Exception:
        logger.debug("context inject digests load failed", exc_info=True)
    return {}


def persist_inject_digests(
    user_id: Any,
    conversation_id: uuid.UUID | None,
    agent_key: str,
    updated_digests: dict[str, str],
) -> None:
    if not updated_digests or conversation_id is None or not isinstance(user_id, uuid.UUID):
        return
    try:
        from apps.backend.infrastructure.agent_runtime.conversation_inject_digest_store import (
            get_inject_digests,
            set_inject_digests,
        )

        merged = get_inject_digests(user_id, conversation_id)
        merged[agent_key] = updated_digests
        set_inject_digests(user_id, conversation_id, merged)
    except Exception:
        logger.debug("context inject digests save failed", exc_info=True)


def needs_full_reinject(context_prep_meta: dict[str, Any], messages: list[Any]) -> bool:
    """True after compaction or every ``CHAT_CONTEXT_INJECT_REFRESH_EVERY_N_TURNS`` user turns."""
    if context_prep_meta.get("compaction_applied"):
        return True
    user_turns = sum(
        1
        for m in messages
        if isinstance(m, dict) and str(m.get("role") or "").lower() == "user"
    )
    refresh_n = int(getattr(config, "CHAT_CONTEXT_INJECT_REFRESH_EVERY_N_TURNS", 8) or 0)
    return refresh_n > 0 and user_turns > 0 and user_turns % refresh_n == 0


def apply_omit_stub_and_ledger(
    messages: list[dict[str, Any]],
    inject_tok: Any,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Append the ephemeral omit stub and return the messages plus this turn's inject ledger."""
    from apps.backend.domain.agent_runtime.context_injection import (
        inject_omit_stub,
        take_inject_ledger,
        take_omitted_injects,
    )

    omitted = take_omitted_injects()
    stub = inject_omit_stub(omitted)
    if stub:
        # Bypass ledger hashing — stub is ephemeral guidance.
        if messages and messages[0].get("role") == "system":
            messages = [
                {
                    **messages[0],
                    "content": (str(messages[0].get("content") or "") + "\n\n" + stub).strip(),
                },
                *messages[1:],
            ]
        else:
            messages = [{"role": "system", "content": stub}, *messages]

    context_injections = take_inject_ledger(inject_tok)
    if stub and omitted:
        context_injections.append(
            {
                "kind": "context_omit_stub",
                "label": f"Stable context omitted ({len(omitted)})",
                "body": stub,
                "chars": len(stub),
                "truncated": False,
                "unchanged": False,
            }
        )
    return messages, context_injections
