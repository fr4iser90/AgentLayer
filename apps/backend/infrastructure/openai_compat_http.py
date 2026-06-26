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


def _normalize_chat_messages_for_templates(messages: Any) -> Any:
    """
    Some llama.cpp/Jinja chat templates require ``system`` messages to appear only
    before the first conversation turn. Keep initial system content as system,
    but preserve later runtime hints in-place as user-visible server notes.
    """
    if not isinstance(messages, list):
        return messages

    system_parts: list[str] = []
    out: list[Any] = []
    saw_non_system = False

    for msg in messages:
        if not isinstance(msg, dict):
            out.append(msg)
            saw_non_system = True
            continue

        role = msg.get("role")
        if role != "system":
            out.append(msg)
            saw_non_system = True
            continue

        content = msg.get("content")
        if not saw_non_system:
            if isinstance(content, str) and content.strip():
                system_parts.append(content.strip())
            elif content:
                system_parts.append(str(content))
            continue

        note = content if isinstance(content, str) else str(content or "")
        out.append(
            {
                **msg,
                "role": "user",
                "content": f"[Server note]\n{note.strip()}".strip(),
            }
        )

    if system_parts:
        out.insert(0, {"role": "system", "content": "\n\n".join(system_parts)})
    return out


def _normalize_chat_request_body(json_body: dict[str, Any]) -> dict[str, Any]:
    needs_copy = "tools" in json_body or "messages" in json_body
    body = copy.deepcopy(json_body) if needs_copy else json_body
    if "tools" in body:
        body["tools"] = _openai_strict_tools(body["tools"])
    if "messages" in body:
        body["messages"] = _normalize_chat_messages_for_templates(body["messages"])
    return body


def http_post_json(
    url: str,
    json_body: dict[str, Any],
    *,
    headers: dict[str, str] | None = None,
    timeout: float | None = None,
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
    timeout: float | None = None,
    concurrency_provider_id: str | None = None,
) -> tuple[dict[str, Any], bool]:
    """
    POST to OpenAI-compatible ``…/chat/completions``.

    Normalizes ``tools[]`` for strict backends (maps ``TOOL_DESCRIPTION`` → ``description``).

    Returns ``(response_json, tools_omitted)`` — ``tools_omitted`` is always ``False`` (reserved).
    """
    h = headers or {"Content-Type": "application/json"}
    body = _normalize_chat_request_body(json_body)
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
