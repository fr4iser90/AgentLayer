"""OpenAI-compatible chat calls via the unified LLM provider catalog (no hardcoded URLs)."""

from __future__ import annotations

import logging
from typing import Any

from apps.backend.core.config import config
from apps.backend.infrastructure.model_catalog_providers import (
    CatalogProviderSpec,
    fetch_models_for_provider,
    get_provider_spec,
    list_provider_specs,
    normalize_catalog_provider_id,
    provider_request_headers,
)
from apps.backend.infrastructure.model_catalog_providers import _chat_completions_url
from apps.backend.infrastructure.openai_compat_http import http_post_chat_completions

logger = logging.getLogger(__name__)

def resolve_provider_id(raw: str | None) -> str | None:
    pid = normalize_catalog_provider_id(raw)
    if not pid:
        return None
    if get_provider_spec(pid) is not None:
        return pid
    return pid


def resolve_catalog_provider(*, provider_id: str | None = None) -> CatalogProviderSpec:
    for candidate in (
        provider_id,
        getattr(config, "LLM_AUX_PROVIDER_ID", None),
        getattr(config, "LLM_ROUTER_PROVIDER_ID", None),
        "provider_1",
    ):
        pid = resolve_provider_id(str(candidate).strip() if candidate else None)
        if not pid:
            continue
        spec = get_provider_spec(pid)
        if spec is not None and spec.base_url.strip():
            return spec
    specs = list_provider_specs()
    if specs:
        return specs[0]
    raise ValueError(
        "No LLM providers configured. Set LLM_PROVIDER_1_BASE_URL (and optional _2, _3, …) "
        "or add endpoints under Admin → Interfaces → LLM-Endpoints."
    )


def resolve_aux_model(spec: CatalogProviderSpec, model: str | None = None) -> str:
    explicit = (model or "").strip()
    if explicit:
        return explicit[:256]
    aux = (getattr(config, "LLM_AUX_MODEL", None) or "").strip()
    if aux:
        return aux[:256]
    if spec.model_default:
        return spec.model_default[:256]
    rows, meta = fetch_models_for_provider(spec, timeout=10.0)
    if meta.get("reachable") and rows:
        mid = str(rows[0].get("id") or "").strip()
        if mid:
            return mid[:256]
    raise ValueError(
        f"Provider {spec.provider_id!r} has no model for this request. "
        "Set LLM_AUX_MODEL, model_default on the provider, or pass an explicit model id."
    )


def post_catalog_chat_completions(
    *,
    messages: list[dict[str, Any]],
    model: str | None = None,
    provider_id: str | None = None,
    timeout: float = 120.0,
    temperature: float | None = None,
    max_tokens: int | None = None,
    stream: bool = False,
    extra_body: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], bool]:
    spec = resolve_catalog_provider(provider_id=provider_id)
    effective_model = resolve_aux_model(spec, model)
    url = _chat_completions_url(spec)
    headers = provider_request_headers(spec)
    body: dict[str, Any] = {
        "model": effective_model,
        "messages": messages,
        "stream": stream,
    }
    if temperature is not None:
        body["temperature"] = temperature
    if max_tokens is not None:
        body["max_tokens"] = max_tokens
    if extra_body:
        body.update(extra_body)
    logger.debug(
        "catalog_llm: provider=%s url=%s model=%r",
        spec.provider_id,
        url,
        effective_model,
    )
    return http_post_chat_completions(
        url,
        body,
        headers=headers,
        timeout=timeout,
        concurrency_provider_id=spec.provider_id,
    )
