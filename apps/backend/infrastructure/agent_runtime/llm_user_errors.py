"""Map low-level HTTP client failures to stable, user-facing strings."""

from __future__ import annotations

import json
import re

import httpx

_SAFE_HINT_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,63}$")


def _request_url_from_exc(exc: BaseException) -> str:
    """Best-effort URL from ``httpx`` transport errors (e.g. chat/completions POST)."""
    req = None
    try:
        req = exc.request  # type: ignore[attr-defined]
    except Exception:
        return ""
    if req is None:
        return ""
    u = getattr(req, "url", None)
    if u is None:
        return ""
    try:
        return str(u)
    except Exception:
        return ""


def _safe_provider_error_hint(response: httpx.Response) -> str:
    """
    Extract a short, client-safe machine reason from a provider error body.

    Prefer JSON ``error`` (string or ``error.code`` / ``error.message``) when it looks
    like a stable code (e.g. ``local_temperature_above_limit``). Never forward raw bodies.
    """
    try:
        raw = (response.text or "").strip()
    except Exception:
        return ""
    if not raw:
        return ""
    obj: object | None
    try:
        obj = response.json()
    except Exception:
        try:
            obj = json.loads(raw)
        except Exception:
            obj = None
    if not isinstance(obj, dict):
        return ""
    err = obj.get("error")
    candidates: list[str] = []
    if isinstance(err, str):
        candidates.append(err.strip())
    elif isinstance(err, dict):
        for key in ("code", "type", "error", "message"):
            val = err.get(key)
            if isinstance(val, str) and val.strip():
                candidates.append(val.strip())
                break
    for key in ("code", "detail"):
        val = obj.get(key)
        if isinstance(val, str) and val.strip():
            candidates.append(val.strip())
    for cand in candidates:
        # Prefer snake/machine codes; allow short human tokens without spaces.
        token = cand.split(":", 1)[0].strip()
        if " " in token:
            token = token.replace(" ", "_")
        if _SAFE_HINT_RE.match(token):
            return token
    return ""


def user_visible_llm_transport_error(exc: BaseException) -> tuple[str, bool]:
    """
    Return ``(message_for_user, log_with_exc_info)``.

    When ``log_with_exc_info`` is False, callers should log with ``logger.warning`` (no traceback)
    for known transport classes; unexpected errors use ``logger.exception``.
    """
    if isinstance(exc, httpx.TimeoutException):
        url = _request_url_from_exc(exc)
        raw = (str(exc) or "").strip()
        parts = [
            "Language model server timeout: the endpoint did not send a response in time. "
            "Common causes: a large or busy model, server overload, or a reverse proxy in front of "
            "the LLM (for example nginx `proxy_read_timeout`) that is shorter than generation time. "
            "Unset AGENT_LLM_CHAT_TIMEOUT_SEC (or set 0) for no AgentLayer HTTP timeout.",
        ]
        if url:
            parts.append(f"POST {url}")
        if raw and raw not in url:
            parts.append(f"({exc.__class__.__name__}: {raw})")
        return (" ".join(parts), False)
    if isinstance(exc, httpx.ConnectError):
        url = _request_url_from_exc(exc)
        raw = (str(exc) or "").strip()
        parts = [
            "Chat LLM connection failed (this is the chat/completions HTTP call to your configured "
            "model server — not RAG/embeddings).",
            "Embeddings use EMBEDDING_PROVIDER_N_* (RAG, memory, Qdrant code index, tool ranking); "
            "it does not change chat. Chat uses LLM_PROVIDER_N_* and Admin LLM endpoints; "
            "model/catalog selection from the UI.",
        ]
        if url:
            parts.append(f"POST {url}")
        if raw and raw not in (url, ""):
            parts.append(f"Reason: {raw}")
        parts.append(
            "Typical fix from Docker: the host inside the container must reach that URL "
            "(LAN IPs like 192.168.x.x are often wrong from a bridge network; use a public hostname, "
            "host.docker.internal, or host networking if appropriate)."
        )
        return (" ".join(parts), False)
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        hint = _safe_provider_error_hint(exc.response)
        if hint:
            return (
                f"Language model server returned HTTP {code} ({hint}). "
                "Inspect logs on the LLM host or proxy.",
                False,
            )
        return (
            f"Language model server returned HTTP {code}. Inspect logs on the LLM host or proxy.",
            False,
        )
    if isinstance(exc, httpx.RequestError):
        url = _request_url_from_exc(exc)
        raw = (str(exc) or "").strip()
        tail = f" POST {url}" if url else ""
        extra = f" ({raw})" if raw else ""
        return (
            f"Request to the language model server failed ({exc.__class__.__name__}){extra}.{tail} "
            "This is the chat endpoint, not embeddings.",
            False,
        )
    return (
        "An unexpected error occurred while running the agent. See AgentLayer server logs for details.",
        True,
    )
