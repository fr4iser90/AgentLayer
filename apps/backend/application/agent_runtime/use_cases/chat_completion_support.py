"""Support helpers for :mod:`apps.backend.application.agent_runtime.use_cases.chat_completion`.

Kept in a separate module so ``chat_completion`` stays under the project's
per-file size limit while these plumbing helpers stay readable instead of being
crushed onto single long lines.
"""
from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from apps.backend.application.agent_runtime.runtime.io import _async_iter_chat_completion_sse
from apps.backend.application.agent_runtime.runtime.tool_loop import _BODY_KEYS_STRIP_FROM_LLM
from apps.backend.domain.model_routing.resolution import ModelRoutingSettings
from apps.backend.infrastructure.platform.config import config


def _model_routing_settings() -> ModelRoutingSettings:
    return ModelRoutingSettings(
        profile_default=config.AGENT_MODEL_PROFILE_DEFAULT,
        profile_vlm=config.AGENT_MODEL_PROFILE_VLM,
        profile_agent=config.AGENT_MODEL_PROFILE_AGENT,
        profile_coding=config.AGENT_MODEL_PROFILE_CODING,
        allow_model_override=config.AGENT_ALLOW_MODEL_OVERRIDE,
        override_roles=config.AGENT_MODEL_OVERRIDE_ROLES,
        override_anonymous=config.AGENT_MODEL_OVERRIDE_ANONYMOUS,
    )


def _as_type_or_none(value: Any, kind: type) -> Any:
    """Return ``value`` unchanged when it matches ``kind``; otherwise ``None``."""
    return value if isinstance(value, kind) else None


def _passthrough_llm_options(body: dict[str, Any]) -> dict[str, Any]:
    """Body minus the keys the tool loop owns, for the raw upstream passthrough."""
    skip = ("messages", "model", "tools", "stream", *_BODY_KEYS_STRIP_FROM_LLM)
    return {k: v for k, v in body.items() if k not in skip}


async def _sse_chat_stream(
    attempts: list[Any],
    payload_stream_base: dict[str, Any],
    llm_backend: str | None,
    profile_key: str | None,
    timeout: int,
    model_routing_settings: ModelRoutingSettings,
) -> AsyncIterator[bytes]:
    async for chunk in _async_iter_chat_completion_sse(
        attempts,
        payload_stream_base,
        llm_backend=llm_backend,
        profile_key=profile_key,
        timeout=timeout,
        model_routing_settings=model_routing_settings,
    ):
        yield chunk
