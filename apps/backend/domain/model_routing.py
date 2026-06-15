"""
Hybrid chat model resolution: profile defaults (VLM / agent / coding), optional client override.

See docs/WEBUI_CONTRACT.md (model routing) and env AGENT_MODEL_* / AGENT_ALLOW_MODEL_OVERRIDE.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from apps.backend.core.config import config

logger = logging.getLogger(__name__)

# Profile ids (not raw model names). Open WebUI may send body ``model: "agent"`` so the
# server picks ``AGENT_MODEL_PROFILE_AGENT`` (delegated / hybrid routing).
_PROFILE_KEYS = frozenset({"default", "vlm", "agent", "coding"})


def _message_content_parts(msg: dict[str, Any]) -> list[dict[str, Any]]:
    """OpenAI-style ``content`` as list, or JSON array string (agent-ui storage format)."""
    c = msg.get("content")
    if isinstance(c, list):
        return [p for p in c if isinstance(p, dict)]
    if isinstance(c, str):
        t = c.strip()
        if t.startswith("["):
            try:
                p = json.loads(c)
                if isinstance(p, list):
                    return [x for x in p if isinstance(x, dict)]
            except json.JSONDecodeError:
                pass
    return []


def messages_contain_image_parts(messages: list[dict[str, Any]]) -> bool:
    """True if any message content uses OpenAI-style multimodal image parts."""
    for m in messages:
        if not isinstance(m, dict):
            continue
        for part in _message_content_parts(m):
            t = str(part.get("type") or "").strip().lower()
            if t in ("image_url", "image", "input_image"):
                return True
            if t == "file" and isinstance(part.get("file"), dict):
                return True
    return False


def _normalize_profile(raw: str | None) -> str:
    if not raw or not str(raw).strip():
        return "default"
    k = str(raw).strip().lower()
    return k if k in _PROFILE_KEYS else "default"


def _profile_token_from_body(body_model: Any) -> str | None:
    """If JSON ``model`` is a reserved profile token, return it; else None."""
    s = _strip_model(body_model)
    if not s:
        return None
    k = s.lower()
    return k if k in _PROFILE_KEYS else None


def _model_for_profile(profile: str) -> str:
    """Env profile hints only; chat completions must finalize via ``catalog_chat_llm`` (no env default model id)."""
    if profile == "vlm":
        return (config.AGENT_MODEL_PROFILE_VLM or "").strip()
    if profile == "agent":
        return (config.AGENT_MODEL_PROFILE_AGENT or "").strip()
    if profile == "coding":
        return (config.AGENT_MODEL_PROFILE_CODING or "").strip()
    return (config.AGENT_MODEL_PROFILE_DEFAULT or "").strip()


def profile_default_model_id(profile: str) -> str:
    """Default model id for ``default`` / ``vlm`` / ``agent`` / ``coding`` (env ``AGENT_MODEL_*``)."""
    return _model_for_profile(_normalize_profile(profile))

def _strip_model(s: Any) -> str | None:
    if s is None:
        return None
    if isinstance(s, str):
        t = s.strip()
        return t or None
    t = str(s).strip()
    return t or None


def _override_allowed(bearer_user_role: str | None) -> bool:
    if not config.AGENT_ALLOW_MODEL_OVERRIDE:
        return False
    if bearer_user_role is None:
        return bool(config.AGENT_MODEL_OVERRIDE_ANONYMOUS)
    allowed_roles = config.AGENT_MODEL_OVERRIDE_ROLES
    if not allowed_roles:
        return True
    return bearer_user_role.strip().lower() in allowed_roles


def resolve_effective_model(
    *,
    messages: list[dict[str, Any]],
    body_model: Any,
    profile_header: str | None,
    override_header: str | None,
    bearer_user_role: str | None,
    embedded_subagent: bool = False,
) -> tuple[str, str, str, bool]:
    """
    Pick the logical model id for this chat completion (catalog provider when primary is local;
    same string is reused for OpenAI-style overrides when primary is external).

    Returns ``(model_id, reason, profile_key, is_override)`` where ``profile_key`` is
    ``default`` / ``vlm`` / ``agent`` / ``coding``, and ``is_override`` is True when a
    per-request model override won (header/body).
    """
    if embedded_subagent and not messages_contain_image_parts(messages):
        bm = _strip_model(body_model)
        if bm and bm.lower() not in _PROFILE_KEYS:
            logger.info(
                "model routing: embedded_subagent inherit parent model %r (skip anonymous override gate)",
                bm,
            )
            return bm, "embedded_subagent:inherit_parent", "default", True

    auto_vlm = messages_contain_image_parts(messages)
    if auto_vlm:
        profile = "vlm"
        base = _model_for_profile("vlm")
        reason_base = "auto:vlm_images"
    else:
        hdr = (profile_header or "").strip()
        body_tok = _profile_token_from_body(body_model)
        if hdr:
            profile = _normalize_profile(hdr)
        elif body_tok:
            profile = body_tok
        else:
            profile = "default"
        base = _model_for_profile(profile)
        reason_base = f"profile:{profile}" + (
            f" (body.model token)" if body_tok and not hdr else ""
        )

    # Text-only overrides (e.g. lfm2.5-thinking) cannot consume image_url parts — local stack may error.
    if _override_allowed(bearer_user_role) and not auto_vlm:
        oh = _strip_model(override_header)
        bm = _strip_model(body_model)
        if _profile_token_from_body(body_model):
            bm = None
        chosen = oh or bm
        if chosen:
            logger.info(
                "model routing: %s -> override %r (allow_override role=%r)",
                reason_base,
                chosen,
                bearer_user_role,
            )
            return chosen, "override:header" if oh else "override:body", profile, True
    if auto_vlm and _override_allowed(bearer_user_role):
        oh = _strip_model(override_header)
        bm = _strip_model(body_model)
        if _profile_token_from_body(body_model):
            bm = None
        if oh or bm:
            logger.info(
                "model routing: %s — ignoring model override %r (conversation has images; "
                "using VLM profile model %r)",
                reason_base,
                oh or bm,
                base,
            )

    logger.info(
        "model routing: %s effective=%r (profile=%s)",
        reason_base,
        base,
        profile,
    )
    return base, reason_base, profile, False
