"""
Unified OpenAI-compatible LLM catalog providers.

Every chat stack (Ollama, llama.cpp, OpenAI, Anthropic-via-proxy, …) is a
:class:`CatalogProviderSpec` with the same fetch + route logic. Configure via:

- **Admin → Interfaces → LLM-Endpoints** (``operator_external_llm_endpoints``), or
- **Legacy env bootstrap** (optional): ``OLLAMA_BASE_URL``, ``LLAMA_CPP_*`` → same shape as DB rows.

No per-vendor Python modules. Pick provider + model in the UI → ``agent_model_catalog_owned_by``.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from typing import Any, Literal

import httpx

from apps.backend.core.config import config
from apps.backend.infrastructure.db import db

logger = logging.getLogger(__name__)

LlmStack = Literal["ollama", "external", "llama_cpp"]

_EXTERNAL_LEGACY_ID = "external"
_EXTERNAL_PREFIX = "external_"

_HDR_NAME_TOKEN = re.compile(r"^[!#$%&'*+.0-9A-Z^_`a-z|~-]{1,128}\Z")

_SPECS_CACHE: tuple[float, list[CatalogProviderSpec]] | None = None
_SPECS_CACHE_TTL_SEC = 2.0


@dataclass(frozen=True)
class CatalogProviderSpec:
    """One OpenAI-compatible chat endpoint (= one ``owned_by`` in GET ``/v1/models``)."""

    provider_id: str
    label: str
    base_url: str
    api_key: str
    api_header_name: str
    model_default: str | None = None
    model_vlm: str | None = None
    model_agent: str | None = None
    model_coding: str | None = None
    source: str = "db"
    db_endpoint_id: int | None = None


def normalize_catalog_provider_id(raw: Any) -> str | None:
    if raw is None:
        return None
    s = str(raw).strip().lower()
    t = "".join(c for c in s if c.isalnum() or c in "_-")[:64]
    if not t:
        return None
    if t == "llamacpp":
        t = "llama_cpp"
    return t


def external_provider_id(endpoint_id: int) -> str:
    return f"{_EXTERNAL_PREFIX}{int(endpoint_id)}"


def parse_external_provider_id(provider_id: str) -> int | None:
    if not provider_id.startswith(_EXTERNAL_PREFIX):
        return None
    suffix = provider_id[len(_EXTERNAL_PREFIX) :]
    if suffix.isdigit():
        return int(suffix)
    return None


def merge_model_catalog_rows(*row_lists: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str]] = set()
    out: list[dict[str, Any]] = []
    for rows in row_lists:
        for row in rows:
            rid = str(row.get("id") or "").strip()
            ob = str(row.get("owned_by") or "").strip()
            if not rid or not ob:
                continue
            key = (ob, rid)
            if key in seen:
                continue
            seen.add(key)
            out.append(row)
    return out


def _strip_env_value(raw: str | None) -> str:
    s = (raw or "").strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in ('"', "'"):
        s = s[1:-1].strip()
    return s


def _strip_opt(s: Any) -> str | None:
    if s is None:
        return None
    t = str(s).strip()
    return t or None


def _valid_http_header_name(name: str) -> bool:
    s = name.strip()
    return bool(s) and bool(_HDR_NAME_TOKEN.match(s))


def _coerce_api_header_name_and_secret(header_name: str, secret: str) -> tuple[str, str]:
    hn = (header_name or "").strip()[:128]
    key = (secret or "").strip()[:512]
    if hn.lower() == "authorization":
        return hn, key
    if _valid_http_header_name(hn):
        return hn, key
    if key and _valid_http_header_name(key):
        logger.warning(
            "llm provider: API header name %r is not a valid token — swapping name/value",
            hn[:80],
        )
        return key, hn
    if not key and hn:
        return "X-API-KEY", hn
    return hn or "Authorization", key


def provider_request_headers(spec: CatalogProviderSpec) -> dict[str, str]:
    from apps.backend.infrastructure.operator_settings import external_api_headers

    base = spec.base_url.rstrip("/")
    key = spec.api_key
    if spec.api_header_name.strip().lower() == "authorization" or (
        not spec.api_header_name.strip() and key
    ):
        return external_api_headers(base, key)
    hn, secret = _coerce_api_header_name_and_secret(spec.api_header_name, key)
    out: dict[str, str] = {"Content-Type": "application/json"}
    if hn.lower() == "authorization":
        if secret:
            out["Authorization"] = (
                secret if secret.lower().startswith("bearer ") else f"Bearer {secret}"
            )
        return out
    out[hn] = secret
    return out


def _models_list_url(spec: CatalogProviderSpec) -> str | None:
    from apps.backend.infrastructure.operator_settings import external_models_list_url

    base = spec.base_url.strip().rstrip("/")
    if not base:
        return None
    return external_models_list_url(base)


def _chat_completions_url(spec: CatalogProviderSpec) -> str:
    from apps.backend.infrastructure.operator_settings import (
        external_chat_completions_url,
        normalize_external_llm_base_url,
    )

    bu = normalize_external_llm_base_url(spec.base_url) or spec.base_url.rstrip("/")
    return external_chat_completions_url(bu)


def resolve_model_for_provider(
    spec: CatalogProviderSpec,
    profile_key: str,
    is_override: bool,
    model_from_resolution: str,
) -> str:
    pk = (profile_key or "default").strip().lower()
    if pk not in ("default", "vlm", "agent", "coding"):
        pk = "default"

    def pick(*vals: str | None) -> str | None:
        for v in vals:
            if v and str(v).strip():
                return str(v).strip()[:256]
        return None

    if pk == "vlm":
        prof = pick(spec.model_vlm, spec.model_default)
    elif pk == "agent":
        prof = pick(spec.model_agent, spec.model_default)
    elif pk == "coding":
        prof = pick(spec.model_coding, spec.model_default)
    else:
        prof = pick(spec.model_default)

    if is_override:
        raw = (model_from_resolution or "").strip()
        if raw and ":" in raw:
            logger.info(
                "llm: model override looks like provider:model (%r); using profile model",
                raw,
            )
            if prof:
                return prof
        elif raw:
            return raw[:256]
    if prof:
        return prof
    return (model_from_resolution or "").strip()[:256] or "default"


def _llm_stack_for_provider_id(provider_id: str) -> LlmStack:
    pid = normalize_catalog_provider_id(provider_id) or ""
    if pid == "ollama":
        return "ollama"
    if pid == "llama_cpp":
        return "llama_cpp"
    return "external"


def _env_ollama_spec() -> CatalogProviderSpec | None:
    base = _strip_env_value(getattr(config, "OLLAMA_BASE_URL", None)).rstrip("/")
    if not base:
        return None
    return CatalogProviderSpec(
        provider_id="ollama",
        label="Ollama",
        base_url=base,
        api_key="",
        api_header_name="Authorization",
        source="env_ollama",
    )


def _env_llama_cpp_spec() -> CatalogProviderSpec | None:
    base = _strip_env_value(getattr(config, "LLAMA_CPP_BASE_URL", None)).rstrip("/")
    hn = _strip_env_value(getattr(config, "LLAMA_CPP_API_HEADER_NAME", None)) or "Authorization"
    key = _strip_env_value(getattr(config, "LLAMA_CPP_API_HEADER_VALUE", None)) or ""
    source = "env_llama_cpp"
    model_default = _strip_opt(getattr(config, "LLAMA_CPP_MODEL_DEFAULT", None))
    model_vlm = _strip_opt(getattr(config, "LLAMA_CPP_MODEL_VLM", None))
    model_agent = _strip_opt(getattr(config, "LLAMA_CPP_MODEL_AGENT", None))
    model_coding = _strip_opt(getattr(config, "LLAMA_CPP_MODEL_CODING", None))

    if not base:
        from apps.backend.infrastructure.operator_settings import _cached_row

        r = _cached_row()
        base = _strip_opt(r.get("llama_cpp_api_base")) or ""
        if base:
            base = base.rstrip("/")
            hn = _strip_opt(r.get("llama_cpp_api_header_name")) or hn
            key = _strip_opt(r.get("llama_cpp_api_key")) or key
            model_default = _strip_opt(r.get("llama_cpp_model_default")) or model_default
            model_vlm = _strip_opt(r.get("llama_cpp_model_vlm")) or model_vlm
            model_agent = _strip_opt(r.get("llama_cpp_model_agent")) or model_agent
            model_coding = _strip_opt(r.get("llama_cpp_model_coding")) or model_coding
            source = "env_llama_cpp_admin"

    if not base:
        return None

    return CatalogProviderSpec(
        provider_id="llama_cpp",
        label="llama.cpp",
        base_url=base,
        api_key=key,
        api_header_name=hn,
        model_default=model_default,
        model_vlm=model_vlm,
        model_agent=model_agent,
        model_coding=model_coding,
        source=source,
    )


def _db_endpoint_spec(row: dict[str, Any]) -> CatalogProviderSpec:
    from apps.backend.infrastructure.operator_settings import normalize_external_llm_base_url

    eid = int(row["id"])
    bu = normalize_external_llm_base_url(_strip_opt(row.get("base_url"))) or ""
    return CatalogProviderSpec(
        provider_id=external_provider_id(eid),
        label=(_strip_opt(row.get("label")) or f"LLM #{eid}")[:128],
        base_url=bu,
        api_key=_strip_opt(row.get("api_key")) or "",
        api_header_name="Authorization",
        model_default=_strip_opt(row.get("model_default")),
        model_vlm=_strip_opt(row.get("model_vlm")),
        model_agent=_strip_opt(row.get("model_agent")),
        model_coding=_strip_opt(row.get("model_coding")),
        source="db",
        db_endpoint_id=eid,
    )


def list_provider_specs(*, force_refresh: bool = False) -> list[CatalogProviderSpec]:
    global _SPECS_CACHE
    now = time.monotonic()
    if (
        not force_refresh
        and _SPECS_CACHE is not None
        and now - _SPECS_CACHE[0] <= _SPECS_CACHE_TTL_SEC
    ):
        return list(_SPECS_CACHE[1])

    specs: list[CatalogProviderSpec] = []
    seen: set[str] = set()

    for bootstrap in (_env_ollama_spec(), _env_llama_cpp_spec()):
        if bootstrap and bootstrap.provider_id not in seen:
            specs.append(bootstrap)
            seen.add(bootstrap.provider_id)

    for row in db.external_llm_endpoints_list_all():
        sp = _db_endpoint_spec(row)
        if sp.provider_id in seen:
            continue
        if sp.base_url:
            specs.append(sp)
            seen.add(sp.provider_id)

    _SPECS_CACHE = (now, specs)
    return list(specs)


def get_provider_spec(provider_id: str) -> CatalogProviderSpec | None:
    pid = normalize_catalog_provider_id(provider_id)
    if not pid:
        return None
    for spec in list_provider_specs():
        if spec.provider_id == pid:
            return spec
    return None


def fetch_models_for_provider(
    spec: CatalogProviderSpec,
    timeout: float = 15.0,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """``(model_rows, agentlayer_meta)`` for this provider."""
    meta: dict[str, Any] = {
        "label": spec.label,
        "reachable": False,
        "detail": None,
        "source": spec.source,
    }
    if spec.db_endpoint_id is not None:
        meta["endpoint_id"] = spec.db_endpoint_id

    url = _models_list_url(spec)
    if not url:
        meta["detail"] = "not_configured"
        return [], meta

    if spec.provider_id == "ollama" and not spec.api_key:
        from apps.backend.infrastructure.openai_compat_http import http_get_json

        status, text, data = http_get_json(url, timeout=timeout)
        if status != 200 or not isinstance(data, dict):
            tag = "timeout" if status == 408 else "connect_error" if status == 503 else f"http_{status}"
            meta["detail"] = (text or "").strip() or tag
            return [], meta
        meta["reachable"] = True
        rows = _parse_models_payload(data, spec.provider_id)
        return rows, meta

    headers = provider_request_headers(spec)
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.get(url, headers=headers)
        status, text, data = (
            resp.status_code,
            resp.text,
            resp.json() if resp.status_code == 200 else None,
        )
    except httpx.TimeoutException:
        status, text, data = 408, "timeout", None
    except httpx.RequestError as e:
        status, text, data = 503, str(e)[:500], None

    if status != 200 or not isinstance(data, dict):
        tag = "timeout" if status == 408 else "connect_error" if status == 503 else f"http_{status}"
        meta["detail"] = (text or "").strip() or tag
        if status in (401, 403):
            meta["auth_hint"] = (
                "401/403: check API key / header name for this LLM endpoint (Admin → Interfaces)."
            )
        meta["models_url"] = url
        meta["header_name"] = spec.api_header_name
        meta["header_value_configured"] = bool(spec.api_key)
        return [], meta

    meta["reachable"] = True
    meta["models_url"] = url
    return _parse_models_payload(data, spec.provider_id), meta


def _parse_models_payload(data: dict[str, Any], owned_by: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in data.get("data") or []:
        if not isinstance(item, dict):
            continue
        mid = item.get("id")
        if not isinstance(mid, str) or not mid.strip():
            continue
        out.append(
            {
                "id": mid.strip(),
                "object": item.get("object") if isinstance(item.get("object"), str) else "model",
                "owned_by": owned_by,
            }
        )
    return out


def fetch_full_model_catalog() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    agentlayer: dict[str, Any] = {}
    lists: list[list[dict[str, Any]]] = []
    for spec in list_provider_specs():
        rows, meta = fetch_models_for_provider(spec)
        agentlayer[spec.provider_id] = meta
        if rows:
            lists.append(rows)
    merged = merge_model_catalog_rows(*lists)
    try:
        from apps.backend.infrastructure.embedding_client import embedding_catalog_health

        agentlayer["embedding"] = embedding_catalog_health()
    except Exception:
        agentlayer["embedding"] = {
            "configured": False,
            "reachable": False,
            "detail": "embedding_health_probe_failed",
        }
    return merged, agentlayer


def build_model_provider_index() -> dict[str, list[str]]:
    index: dict[str, list[str]] = {}
    for row in fetch_full_model_catalog()[0]:
        mid = str(row.get("id") or "").strip()
        ob = normalize_catalog_provider_id(row.get("owned_by"))
        if not mid or not ob:
            continue
        index.setdefault(mid, [])
        if ob not in index[mid]:
            index[mid].append(ob)
    return index


def route_chat_by_catalog_provider(
    catalog_owned_by: str,
    model_from_resolution: str,
    profile_key: str,
    is_override: bool,
) -> tuple[list[tuple[str, dict[str, str], str]], LlmStack]:
    pid = normalize_catalog_provider_id(catalog_owned_by)
    if not pid:
        raise ValueError("Invalid catalog provider id.")

    if pid == _EXTERNAL_LEGACY_ID:
        from apps.backend.infrastructure.operator_settings import _external_llm_chat_attempts

        attempts = _external_llm_chat_attempts(profile_key, is_override, model_from_resolution)
        if not attempts:
            raise ValueError(
                "Legacy provider id 'external' has no LLM endpoints — use external_N from the catalog "
                "or add endpoints in Admin → Interfaces."
            )
        return attempts, "external"

    spec = get_provider_spec(pid)
    if spec is None:
        raise ValueError(
            f"Unknown catalog provider {catalog_owned_by!r}. "
            "Add it under Admin → Interfaces → LLM-Endpoints (or set OLLAMA_BASE_URL / LLAMA_CPP_* in .env)."
        )

    if not spec.base_url.strip():
        raise ValueError(f"Provider {pid!r} has no base URL configured.")

    chat_url = _chat_completions_url(spec)
    headers = provider_request_headers(spec)
    model = resolve_model_for_provider(spec, profile_key, is_override, model_from_resolution)
    if not model:
        raise ValueError(f"Provider {pid!r} has no model id for this request.")

    logger.info(
        "catalog_route: provider=%s (%s) url=%s model=%r",
        pid,
        spec.source,
        chat_url,
        model,
    )
    return [(chat_url, headers, model)], _llm_stack_for_provider_id(pid)


# --- Backward-compatible helpers (no separate llamacpp module) ---


def llama_cpp_configured() -> bool:
    return get_provider_spec("llama_cpp") is not None


def llama_cpp_chat_endpoint() -> tuple[str, dict[str, str]] | None:
    spec = get_provider_spec("llama_cpp")
    if not spec:
        return None
    return _chat_completions_url(spec), provider_request_headers(spec)


def invalidate_provider_specs_cache() -> None:
    global _SPECS_CACHE
    _SPECS_CACHE = None
