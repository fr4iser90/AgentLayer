"""HTTP helpers for **OpenAI-compatible** LLM endpoints.

Per-provider concurrency slots (``llm_concurrency``) replace the former process-wide lock.
Async call sites should use ``await asyncio.to_thread(http_post_json, ...)`` (see ``domain.agent``).
"""

from __future__ import annotations

import copy
import logging
from typing import Any

import httpx

from apps.backend.infrastructure.llm_concurrency import llm_slot

logger = logging.getLogger(__name__)

# Back-compat for tests/docs that referenced the old global lock.
LLM_HTTP_SERIALIZE_LOCK = None  # noqa: N816 — removed; use llm_concurrency per provider


def _openai_strict_tools(obj: Any) -> Any:
    """
    Some servers tolerate extra JSON-Schema keys like ``TOOL_DESCRIPTION`` on tools; strict
    OpenAI-shaped APIs reject unknown field names. Map ``TOOL_DESCRIPTION`` → ``description``.
    """
    if isinstance(obj, dict):
        has_desc = "description" in obj
        out: dict[str, Any] = {}
        for k, v in obj.items():
            if k == "TOOL_DESCRIPTION":
                if not has_desc:
                    out["description"] = _openai_strict_tools(v)
                continue
            out[k] = _openai_strict_tools(v)
        return out
    if isinstance(obj, list):
        return [_openai_strict_tools(x) for x in obj]
    return obj


def http_post_json(
    url: str,
    json_body: dict[str, Any],
    *,
    headers: dict[str, str] | None = None,
    timeout: float = 600.0,
    concurrency_provider_id: str | None = None,
) -> dict[str, Any]:
    h = headers or {"Content-Type": "application/json"}
    with llm_slot(concurrency_provider_id):
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(url, json=json_body, headers=h)
            resp.raise_for_status()
            return resp.json()


def http_post_chat_completions(
    url: str,
    json_body: dict[str, Any],
    *,
    headers: dict[str, str] | None = None,
    timeout: float = 600.0,
    concurrency_provider_id: str | None = None,
) -> tuple[dict[str, Any], bool]:
    """
    POST to OpenAI-compatible ``…/chat/completions``.

    Normalizes ``tools[]`` for strict backends (maps ``TOOL_DESCRIPTION`` → ``description``).

    Returns ``(response_json, tools_omitted)`` — ``tools_omitted`` is always ``False`` (reserved).
    """
    h = headers or {"Content-Type": "application/json"}
    body = json_body
    if "tools" in json_body:
        body = copy.deepcopy(json_body)
        body["tools"] = _openai_strict_tools(body["tools"])
    with llm_slot(concurrency_provider_id):
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(url, json=body, headers=h)
            resp.raise_for_status()
            return resp.json(), False


def http_get_json(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    timeout: float = 60.0,
) -> tuple[int, str, Any | None]:
    """GET; returns ``(status, text_on_error, json_or_none)``."""
    h = headers or {}
    try:
        with httpx.Client(timeout=timeout) as client:
            r = client.get(url, headers=h)
            if r.status_code != 200:
                return r.status_code, r.text, None
            return 200, "", r.json()
    except httpx.TimeoutException:
        return 408, "timeout", None
    except httpx.RequestError as e:
        return 503, str(e)[:500], None
