from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import httpx

from apps.backend.infrastructure.platform.config import config
from apps.backend.application.agent_runtime.dependencies import (
    external_llm_should_failover,
    http_post_chat_completions,
    llm_chat_transport,
    stream_chat_completions_aggregate,
    unpack_llm_attempt,
)
from apps.backend.application.agent_runtime.runtime.io import _redact_provider_error_text_for_log
from apps.backend.application.agent_runtime.runtime.tool_loop import _thread_with_cancel
from apps.backend.application.agent_runtime.runtime.prompts import AgentChatCancelled
from apps.backend.domain.model_routing.resolution import ModelRoutingSettings, profile_default_model_id

logger = logging.getLogger(__name__)


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


@dataclass
class LlmRoundResult:
    data: dict[str, Any]
    tools_omitted: bool
    chosen: tuple[str, dict[str, str], str, str]
    model: str
    attempts: list[tuple[str, dict[str, str], str, str]]
    llm_backend: str


async def execute_llm_completion_round(
    *,
    attempts: list[tuple[str, dict[str, str], str, str]],
    payload_base: dict[str, Any],
    llm_backend: str,
    profile_key: str,
    use_llm_stream: bool,
    cancel_event: Any,
    on_text_delta: Callable[[str], Awaitable[None]] | None,
    on_reasoning_delta: Callable[[str], Awaitable[None]] | None,
    catalog_owned_by: str | None,
) -> LlmRoundResult:
    while True:
        last_failover: httpx.HTTPStatusError | None = None
        last_transport_error: httpx.RequestError | None = None
        if use_llm_stream:
            try:
                data, tools_omitted, chosen = await stream_chat_completions_aggregate(
                    attempts,
                    dict(payload_base),
                    llm_backend=llm_backend,
                    profile_key=profile_key,
                    on_text_delta=on_text_delta,
                    on_reasoning_delta=on_reasoning_delta,
                    cancel_event=cancel_event,
                    timeout=config.LLM_CHAT_TIMEOUT_SEC,
                )
            except AgentChatCancelled:
                raise
            except httpx.HTTPStatusError:
                raise
            except httpx.RequestError:
                raise
            return LlmRoundResult(
                data=data,
                tools_omitted=tools_omitted,
                chosen=chosen,
                model=chosen[2],
                attempts=attempts,
                llm_backend=llm_backend,
            )

        chosen: tuple[str, dict[str, str], str, str] | None = None
        data: dict[str, Any] = {}
        tools_omitted = False
        for attempt in attempts:
            b_url, b_headers, b_model, b_provider = unpack_llm_attempt(attempt)
            pl = dict(payload_base)
            pl["model"] = b_model
            try:
                data, tools_omitted = await _thread_with_cancel(
                    cancel_event,
                    http_post_chat_completions,
                    b_url,
                    pl,
                    headers=b_headers,
                    timeout=config.LLM_CHAT_TIMEOUT_SEC,
                    concurrency_provider_id=b_provider or None,
                )
                chosen = attempt
                break
            except httpx.RequestError as e:
                last_transport_error = e
                logger.warning(
                    "LLM chat/completions transport error (%s) url=%s model=%s: %s",
                    llm_backend,
                    b_url,
                    b_model,
                    e,
                )
                continue
            except httpx.HTTPStatusError as e:
                last_failover = e
                sc = e.response.status_code
                if llm_backend == "provider_db" and external_llm_should_failover(sc):
                    logger.warning(
                        "LLM external attempt failed (status=%s); trying next endpoint",
                        sc,
                    )
                    continue
                err_body = _redact_provider_error_text_for_log(
                    e.response.text, max_len=600
                )
                logger.error(
                    "LLM chat/completions failed (%s): status=%s llm_model_id=%s body=%s",
                    llm_backend,
                    sc,
                    b_model,
                    err_body,
                )
                raise
        else:
            if last_failover is not None:
                err_body = _redact_provider_error_text_for_log(
                    last_failover.response.text, max_len=600
                )
                if (
                    llm_backend == "provider_db"
                    and last_failover.response.status_code == 429
                ):
                    local_model = profile_default_model_id(profile_key, _model_routing_settings())
                    attempts, llm_backend = llm_chat_transport(
                        local_model,
                        profile_key,
                        False,
                        backend_override="provider",
                        catalog_owned_by=None,
                    )
                    logger.warning(
                        "LLM external: all endpoints returned 429 (quota/rate limit); "
                        "falling back to local catalog provider for this request (llm_model_id=%s). Next rounds use local.",
                        local_model,
                    )
                    continue
                logger.error(
                    "LLM external: all endpoints failed, last status=%s body=%s",
                    last_failover.response.status_code,
                    err_body,
                )
                raise last_failover
            if last_transport_error is not None:
                raise last_transport_error
            raise RuntimeError("LLM: no chat/completions attempts")
        if chosen is None:
            raise RuntimeError("LLM: internal error: no completion chosen after HTTP success")
        return LlmRoundResult(
            data=data,
            tools_omitted=tools_omitted,
            chosen=chosen,
            model=chosen[2],
            attempts=attempts,
            llm_backend=llm_backend,
        )


__all__ = ["LlmRoundResult", "execute_llm_completion_round"]
