"""
Optional **llama.cpp server** (OpenAI-compatible) for local chat completions.

**Configuration (first match wins):**

1. **Environment** — same naming style as ``OLLAMA_*``: if ``LLAMA_CPP_BASE_URL`` is non-empty and
   ``LLAMA_CPP_ENABLED`` is true (default), use ``LLAMA_CPP_*`` from :mod:`apps.backend.core.config`.
   Pair **name + value** like HTTP headers: ``LLAMA_CPP_API_HEADER_NAME`` (e.g. ``X-API-KEY``) and
   ``LLAMA_CPP_API_HEADER_VALUE`` (same string OpenCode puts in ``headers["X-API-KEY"]``).
2. Else **Admin → Interfaces** (``operator_settings``) when ``llama_cpp_enabled`` and base URL are set.

When the client sends ``agent_model_catalog_owned_by: "llama_cpp"`` (from GET ``/v1/models`` row ``owned_by``),
:func:`llm_chat_transport` uses this OpenAI-compatible endpoint for **chat** with the exact ``model`` string from the
request — no substitution from ``llm_primary_backend``. Embeddings and other Ollama-only paths still use
``OLLAMA_BASE_URL`` unless configured separately.

``GET /v1/models`` (see :mod:`apps.backend.api.main`) returns **separate** Ollama and Llama.cpp model lists
(``agentlayer`` + ``owned_by`` on each row) — no silent cross-backend substitution.
"""

from __future__ import annotations

import logging
import re
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# RFC 7230 ``token`` for header field-names; secrets (``@``, spaces, …) fail here → detect mis-pasted .env.
_HDR_NAME_TOKEN = re.compile(r"^[!#$%&'*+.0-9A-Z^_`a-z|~-]{1,128}\Z")


def _valid_http_header_name(name: str) -> bool:
    s = name.strip()
    return bool(s) and bool(_HDR_NAME_TOKEN.match(s))


def _coerce_llama_header_name_and_secret(header_name: str, secret: str) -> tuple[str, str]:
    """
    Fix common .env mistakes: secret in ``LLAMA_CPP_API_HEADER_NAME``, or name/value swapped.
    Returns ``(header_name, secret)`` safe for ``httpx``.
    """
    hn = (header_name or "").strip()[:128]
    key = (secret or "").strip()[:512]
    if hn.lower() == "authorization":
        return hn, key
    if _valid_http_header_name(hn):
        return hn, key
    if key and _valid_http_header_name(key):
        logger.warning(
            "llama_cpp: LLAMA_CPP_API_HEADER_NAME %r is not a valid HTTP header token — swapping name/value "
            "(name → e.g. X-API-KEY, secret → LLAMA_CPP_API_HEADER_VALUE).",
            hn[:80] + ("…" if len(hn) > 80 else ""),
        )
        return key, hn
    if not key and hn:
        logger.warning(
            "llama_cpp: LLAMA_CPP_API_HEADER_NAME %r is not a valid header token — using it as secret with "
            "header name X-API-KEY (OpenCode: headers.X-API-KEY).",
            hn[:80] + ("…" if len(hn) > 80 else ""),
        )
        return "X-API-KEY", hn
    return hn, key


def _effective_header_pair(r: dict[str, Any]) -> tuple[str, str]:
    hn = (str(r.get("llama_cpp_api_header_name") or "").strip() or "Authorization")[:128]
    key = (str(r.get("llama_cpp_api_key") or "").strip())[:512]
    return _coerce_llama_header_name_and_secret(hn, key)


def _settings_row() -> dict[str, Any]:
    from apps.backend.infrastructure.operator_settings import _cached_row

    return _cached_row()


def _llama_effective() -> dict[str, Any]:
    """Subset of operator_settings llama_* keys, sourced from env (if set) else DB row."""
    from apps.backend.core import config as C

    env_base = (getattr(C, "LLAMA_CPP_BASE_URL", "") or "").strip().rstrip("/")
    if env_base and getattr(C, "LLAMA_CPP_ENABLED", True):
        return {
            "llama_cpp_enabled": True,
            "llama_cpp_api_base": env_base,
            "llama_cpp_api_header_name": getattr(C, "LLAMA_CPP_API_HEADER_NAME", None),
            "llama_cpp_api_key": getattr(C, "LLAMA_CPP_API_HEADER_VALUE", None),
            "llama_cpp_router_model": getattr(C, "LLAMA_CPP_ROUTER_MODEL", None),
            "llama_cpp_model_default": getattr(C, "LLAMA_CPP_MODEL_DEFAULT", None),
            "llama_cpp_model_vlm": getattr(C, "LLAMA_CPP_MODEL_VLM", None),
            "llama_cpp_model_agent": getattr(C, "LLAMA_CPP_MODEL_AGENT", None),
            "llama_cpp_model_coding": getattr(C, "LLAMA_CPP_MODEL_CODING", None),
        }
    r = _settings_row()
    return {
        "llama_cpp_enabled": bool(r.get("llama_cpp_enabled")),
        "llama_cpp_api_base": r.get("llama_cpp_api_base"),
        "llama_cpp_api_header_name": r.get("llama_cpp_api_header_name"),
        "llama_cpp_api_key": r.get("llama_cpp_api_key"),
        "llama_cpp_router_model": r.get("llama_cpp_router_model"),
        "llama_cpp_model_default": r.get("llama_cpp_model_default"),
        "llama_cpp_model_vlm": r.get("llama_cpp_model_vlm"),
        "llama_cpp_model_agent": r.get("llama_cpp_model_agent"),
        "llama_cpp_model_coding": r.get("llama_cpp_model_coding"),
    }


def invalidate_cache() -> None:
    """Refresh operator_settings TTL cache (e.g. after tests patch row)."""
    from apps.backend.infrastructure.operator_settings import invalidate_operator_settings_cache

    invalidate_operator_settings_cache()


def enabled() -> bool:
    r = _llama_effective()
    if not bool(r.get("llama_cpp_enabled")):
        return False
    base = str(r.get("llama_cpp_api_base") or "").strip()
    return bool(base)


def chat_completions_url() -> str | None:
    r = _llama_effective()
    if not bool(r.get("llama_cpp_enabled")):
        return None
    base = str(r.get("llama_cpp_api_base") or "").strip().rstrip("/")
    if not base:
        return None
    return f"{base}/chat/completions"


def request_headers() -> dict[str, str]:
    r = _llama_effective()
    out: dict[str, str] = {"Content-Type": "application/json"}
    if not bool(r.get("llama_cpp_enabled")):
        return out
    hn, key = _effective_header_pair(r)
    if hn.lower() == "authorization":
        if not key:
            return out
        out["Authorization"] = f"Bearer {key}"
        return out
    # Custom header (e.g. ``X-API-KEY``): value from env ``LLAMA_CPP_API_HEADER_VALUE`` (internal key ``llama_cpp_api_key``).
    out[hn] = key
    return out


def resolve_chat_model(profile_key: str | None, fallback: str) -> str:
    """
    Map ``profile_key`` (default / vlm / agent / coding) to a model id for the llama.cpp server.

    Falls back to ``llama_cpp_model_default`` or the ``fallback`` from normal routing when unset.
    """
    r = _llama_effective()
    if not bool(r.get("llama_cpp_enabled")):
        return fallback
    pk = (profile_key or "default").strip().lower()
    if pk not in ("default", "vlm", "agent", "coding"):
        pk = "default"
    col = {
        "default": "llama_cpp_model_default",
        "vlm": "llama_cpp_model_vlm",
        "agent": "llama_cpp_model_agent",
        "coding": "llama_cpp_model_coding",
    }[pk]
    for name in (col, "llama_cpp_model_default"):
        v = r.get(name)
        if isinstance(v, str) and v.strip():
            return v.strip()[:256]
    return fallback


def router_model(default: str) -> str:
    """Small classifier model id for smart routing (optional ``llama_cpp_router_model``)."""
    r = _llama_effective()
    if not bool(r.get("llama_cpp_enabled")):
        return default
    rm = r.get("llama_cpp_router_model")
    if isinstance(rm, str) and rm.strip():
        return rm.strip()[:256]
    return resolve_chat_model("agent", default)


def local_chat_endpoint() -> tuple[str, dict[str, str]] | None:
    """Return ``(chat_completions_url, headers)`` when llama.cpp is active in operator_settings."""
    url = chat_completions_url()
    if not url:
        return None
    return url, request_headers()


def openai_models_list_url() -> str | None:
    """OpenAI-style ``GET …/models`` (base usually ends with ``/v1``)."""
    if not enabled():
        return None
    base = str(_llama_effective().get("llama_cpp_api_base") or "").strip().rstrip("/")
    if not base:
        return None
    if base.lower().endswith("/v1"):
        return f"{base}/models"
    return f"{base}/v1/models"


def catalog_auth_meta() -> dict[str, Any]:
    """Non-secret auth shape for ``GET /v1/models`` ``agentlayer`` (debug 401/403)."""
    if not enabled():
        return {}
    r = _llama_effective()
    hn, key = _effective_header_pair(r)
    key_set = bool(key)
    bearer = hn.lower() == "authorization"
    return {
        "header_value_configured": key_set,
        "header_name": hn,
        "sends_authorization_bearer": bearer and key_set,
        "models_url": openai_models_list_url(),
    }


def models_list_auth_hint(http_error_detail: str | None) -> str | None:
    """Short hint when ``GET …/models`` returns 401/403 (no secrets)."""
    d = (http_error_detail or "").strip()
    if not (d.startswith("http_401") or d.startswith("http_403")):
        return None
    r = _llama_effective()
    hn, key = _effective_header_pair(r)
    key_set = bool(key)
    bearer = hn.lower() == "authorization"
    if not key_set:
        if bearer:
            return (
                "401/403: this process has no auth secret — set LLAMA_CPP_API_HEADER_VALUE (Bearer token)."
            )
        return (
            f"401/403 — no value for your custom header in this process. Set LLAMA_CPP_API_HEADER_VALUE to the same "
            f"string as OpenCode's headers[{hn!r}] (with LLAMA_CPP_API_HEADER_NAME already set)."
        )
    if bearer:
        return (
            "401/403: using Authorization: Bearer. If your server expects a raw key header (e.g. OpenCode), "
            "set LLAMA_CPP_API_HEADER_NAME=X-API-KEY and LLAMA_CPP_API_HEADER_VALUE=<secret>."
        )
    return (
        "401/403: verify LLAMA_CPP_API_HEADER_NAME / LLAMA_CPP_API_HEADER_VALUE match the gateway "
        f"(URL, IP allowlist, or WAF can also cause 403). Header name in use: {hn!r}."
    )


def fetch_openai_models_list(timeout: float = 15.0) -> tuple[bool, str | None, list[dict[str, Any]]]:
    """
    Query the configured Llama.cpp OpenAI server for ``GET /v1/models`` (or ``/models`` under ``/v1``).

    Returns ``(reachable, error_detail, rows)`` where each row is ``{id, object, owned_by: "llama_cpp"}``.
    """
    url = openai_models_list_url()
    if not url:
        return False, "not_configured", []
    hdrs = request_headers()
    try:
        with httpx.Client(timeout=timeout) as client:
            r = client.get(url, headers=hdrs)
    except httpx.ConnectError:
        return False, "connect_error", []
    except httpx.TimeoutException:
        return False, "timeout", []
    except OSError as exc:
        return False, str(exc)[:240], []
    except Exception as exc:
        return False, str(exc)[:240], []
    if r.status_code != 200:
        return False, f"http_{r.status_code}", []
    try:
        body = r.json()
    except Exception:
        return False, "invalid_json", []
    if not isinstance(body, dict):
        return False, "invalid_json_shape", []
    rows: list[dict[str, Any]] = []
    for item in body.get("data") or []:
        if not isinstance(item, dict):
            continue
        mid = item.get("id")
        if not isinstance(mid, str) or not mid.strip():
            continue
        rows.append(
            {
                "id": mid.strip(),
                "object": item.get("object") if isinstance(item.get("object"), str) else "model",
                "owned_by": "llama_cpp",
            }
        )
    return True, None, rows
