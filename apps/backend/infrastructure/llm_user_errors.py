"""Map low-level HTTP client failures to stable, user-facing strings."""

from __future__ import annotations

import httpx


def user_visible_llm_transport_error(exc: BaseException) -> tuple[str, bool]:
    """
    Return ``(message_for_user, log_with_exc_info)``.

    When ``log_with_exc_info`` is False, callers should log with ``logger.warning`` (no traceback)
    for known transport classes; unexpected errors use ``logger.exception``.
    """
    if isinstance(exc, httpx.TimeoutException):
        return (
            "Language model server timeout: the endpoint did not send a response in time. "
            "Common causes: a large or busy model, server overload, or a reverse proxy in front of "
            "the LLM (for example nginx `proxy_read_timeout`) that is shorter than generation time. "
            "Try a shorter prompt, fewer tools, or a faster endpoint.",
            False,
        )
    if isinstance(exc, httpx.ConnectError):
        return (
            "Could not connect to the language model server. Check Ollama / llama.cpp URL, DNS, "
            "TLS, and that the service is reachable from the AgentLayer container or host.",
            False,
        )
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        return (
            f"Language model server returned HTTP {code}. Inspect logs on the LLM host or proxy.",
            False,
        )
    if isinstance(exc, httpx.RequestError):
        return (
            f"Request to the language model server failed ({exc.__class__.__name__}). "
            "Check URL configuration and network path.",
            False,
        )
    return (
        "An unexpected error occurred while running the agent. See AgentLayer server logs for details.",
        True,
    )
