"""Serialized HTTP helpers for **OpenAI-compatible** LLM endpoints.

Used for ``/v1/chat/completions`` and related POST/GET regardless of vendor: **Ollama**,
**llama.cpp** (OpenAI server), operator-configured **external** APIs, etc.

A single process-wide lock limits concurrent blocking HTTP (small GPUs / shared hosts).
Async call sites should use ``await asyncio.to_thread(http_post_json, ...)`` (see ``domain.agent``).
"""

from __future__ import annotations

import copy
import logging
import threading
from typing import Any

import httpx

logger = logging.getLogger(__name__)

LLM_HTTP_SERIALIZE_LOCK = threading.Lock()


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
) -> dict[str, Any]:
    h = headers or {"Content-Type": "application/json"}
    with LLM_HTTP_SERIALIZE_LOCK:
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
    with LLM_HTTP_SERIALIZE_LOCK:
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(url, json=body, headers=h)
            resp.raise_for_status()
            return resp.json(), False


def http_get_json(
    url: str,
    *,
    timeout: float = 60.0,
) -> tuple[int, str, Any | None]:
    """GET; returns ``(status, text_on_error, json_or_none)``."""
    try:
        with LLM_HTTP_SERIALIZE_LOCK:
            with httpx.Client(timeout=timeout) as client:
                r = client.get(url)
                if r.status_code != 200:
                    return r.status_code, r.text, None
                return 200, "", r.json()
    except httpx.TimeoutException:
        return 408, "timeout", None
    except httpx.RequestError as e:
        return 503, str(e)[:500], None
