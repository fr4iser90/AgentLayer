"""External LLM provider transport helpers derived from operator settings."""
from __future__ import annotations

import logging
from typing import Any, Literal

from apps.backend.infrastructure.db import db

logger = logging.getLogger(__name__)

def _strip_opt(s: Any) -> str | None:
    if s is None:
        return None
    t = str(s).strip()
    return t or None


def normalize_external_llm_base_url(raw: str | None) -> str:
    """
    Clean operator-stored URL: trim quotes and accidental path suffixes so we do not
    build ``…/v1/chat/completions/v1/chat/completions``.

    Does **not** validate host; see :func:`external_chat_completions_url` for path rules.
    """
    if not raw:
        return ""
    s = str(raw).strip().strip("'\"")
    s = s.rstrip("/")
    low = s.lower()
    for suf in (
        "/v1/chat/completions",
        "/chat/completions",
        "/v1/models",
        "/models",
    ):
        if low.endswith(suf):
            s = s[: -len(suf)].rstrip("/")
            low = s.lower()
    # ``https://host/v1`` + ``/v1/models`` → avoid ``…/v1/v1/models``
    if low.endswith("/v1"):
        s = s[:-3].rstrip("/")
    return s


def external_api_headers(base_url: str, api_key: str) -> dict[str, str]:
    h: dict[str, str] = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    if "generativelanguage.googleapis.com" in base_url.lower():
        h["x-goog-api-key"] = api_key
    return h


def external_chat_completions_url(base_url: str) -> str:
    """
    ``POST`` target for OpenAI-compatible chat completions: ``{base}/v1/chat/completions``.

    Works for OpenAI (base ``https://api.openai.com``) and Gemini OpenAI-compat (base
    ``https://generativelanguage.googleapis.com/v1beta/openai`` →
    ``…/v1beta/openai/v1/chat/completions``). A missing ``v1`` segment under the OpenAI-compat base
    (``…/openai/chat/completions``) returns **404** from Google.
    """
    bu = normalize_external_llm_base_url(base_url) or base_url.rstrip("/")
    return f"{bu.rstrip('/')}/v1/chat/completions"


def external_models_list_url(base_url: str) -> str:
    """``GET`` for OpenAI-style model list (admin); Gemini OpenAI-compat uses ``…/openai/v1/models``."""
    bu = (normalize_external_llm_base_url(base_url) or base_url).rstrip("/")
    return f"{bu}/v1/models"


def resolve_external_llm_credentials_for_catalog(
    base_url_override: str | None,
    api_key_override: str | None,
    endpoint_id: int | None = None,
) -> tuple[str, str]:
    """Host prefix and API key for admin model list (``GET …/v1/models``)."""
    if base_url_override is not None and str(base_url_override).strip():
        bu = normalize_external_llm_base_url(str(base_url_override).strip())
        key = (
            str(api_key_override).strip()
            if api_key_override is not None and str(api_key_override).strip()
            else ""
        )
        if not bu:
            raise ValueError("missing_base_url")
        if not key:
            raise ValueError("missing_api_key")
        return bu, key

    if endpoint_id is not None:
        row = db.operator_provider_endpoint_by_id("chat", int(endpoint_id))
        if not row:
            row = db.external_llm_endpoint_by_id(int(endpoint_id))
        if not row:
            raise ValueError("unknown_endpoint")
        bu = normalize_external_llm_base_url(_strip_opt(row.get("base_url")))
        key = _strip_opt(row.get("api_key")) or ""
        if not bu or not key:
            raise ValueError("missing_api_key")
        return bu, key

    rows = _chat_provider_endpoint_rows()
    if rows:
        row0 = rows[0]
        bu = normalize_external_llm_base_url(_strip_opt(row0.get("base_url")))
        key = _strip_opt(row0.get("api_key")) or ""
        if bu and key:
            return bu, key

    raise ValueError("no_external_endpoint")


def _chat_provider_endpoint_rows() -> list[dict[str, Any]]:
    rows = db.operator_provider_endpoints_list_all("chat")
    return rows if rows else db.external_llm_endpoints_list_all()


def _external_model_for_endpoint_row(
    row: dict[str, Any],
    profile_key: str,
    is_override: bool,
    model_from_resolution: str,
) -> str | None:
    pk = (profile_key or "default").strip().lower()
    if pk not in ("default", "vlm", "agent", "coding"):
        pk = "default"

    def col(name: str) -> str | None:
        return _strip_opt(row.get(name))

    d = col("model_default")
    if pk == "vlm":
        prof = col("model_vlm") or d
    elif pk == "agent":
        prof = col("model_agent") or d
    elif pk == "coding":
        prof = col("model_coding") or d
    else:
        prof = d

    if is_override:
        raw = _strip_opt(model_from_resolution)
        if raw and ":" in raw:
            logger.info(
                "llm: external endpoint but model override looks like a local catalog id (%r); using profile model",
                raw,
            )
            return prof
        return raw
    return prof


def external_llm_should_failover(http_status: int) -> bool:
    """Try next external endpoint on these status codes (quota, auth, overload)."""
    return http_status in (401, 403, 408, 429, 500, 502, 503, 504)


def normalize_model_catalog_owned_by(raw: Any) -> str | None:
    """Opaque catalog provider id from GET ``/v1/models`` row ``owned_by`` (see ``model_catalog_providers``)."""
    from apps.backend.infrastructure.providers.model_catalog_providers import normalize_catalog_provider_id

    return normalize_catalog_provider_id(raw)


def _admin_llm_chat_attempts(
    profile_key: str,
    is_override: bool,
    model_from_resolution: str,
) -> list[tuple[str, dict[str, str], str, str]]:
    return _external_llm_chat_attempts(profile_key, is_override, model_from_resolution)


def _external_llm_chat_attempts(
    profile_key: str,
    is_override: bool,
    model_from_resolution: str,
) -> list[tuple[str, dict[str, str], str, str]]:
    from apps.backend.infrastructure.agent_runtime.llm_chat_attempt import make_llm_attempt
    from apps.backend.infrastructure.providers.model_catalog_providers import db_catalog_provider_id

    pk = (profile_key or "default").strip().lower()
    if pk not in ("default", "vlm", "agent", "coding"):
        pk = "default"
    attempts: list[tuple[str, dict[str, str], str, str]] = []
    for row in _chat_provider_endpoint_rows():
        bu = normalize_external_llm_base_url(_strip_opt(row.get("base_url")))
        key = _strip_opt(row.get("api_key")) or ""
        ext_model = _external_model_for_endpoint_row(row, pk, is_override, model_from_resolution)
        if not bu or not key or not ext_model:
            continue
        chat_url = external_chat_completions_url(bu)
        headers = external_api_headers(bu, key)
        attempts.append(
            make_llm_attempt(
                chat_url,
                headers,
                ext_model,
                db_catalog_provider_id(int(row["id"])),
            )
        )
    return attempts


def llm_chat_transport(
    model_from_resolution: str,
    profile_key: str,
    is_override: bool,
    *,
    backend_override: Literal["provider", "provider_db"] | None = None,
    catalog_owned_by: str | None = None,
) -> tuple[
    list[tuple[str, dict[str, str], str, str]],
    Literal["provider_env", "provider_db"],
]:
    from apps.backend.infrastructure.providers.model_catalog_providers import (
        first_admin_provider_id,
        first_env_provider_id,
        route_chat_by_catalog_provider,
    )

    owned = catalog_owned_by
    if backend_override is not None:
        bo = backend_override.strip().lower() if isinstance(backend_override, str) else ""
        if bo == "provider":
            owned = first_env_provider_id() or owned
        elif bo == "provider_db":
            owned = first_admin_provider_id() or owned

    if owned is None:
        raise ValueError(
            f"Could not determine which LLM provider serves model {model_from_resolution!r}. "
            "Re-select the model in the UI (provider + model) so agent_model_catalog_owned_by is sent."
        )

    return route_chat_by_catalog_provider(
        owned,
        model_from_resolution,
        profile_key,
        is_override,
    )

