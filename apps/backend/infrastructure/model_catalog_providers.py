"""
Unified OpenAI-compatible LLM catalog providers.

Every chat stack is a :class:`CatalogProviderSpec` with the same fetch + route logic. Configure via:

- **Env**: ``LLM_PROVIDER_1_BASE_URL``, ``LLM_PROVIDER_2_*``, … → ``provider_1``, ``provider_2``, …
- **Admin → Interfaces → LLM-Endpoints** → ``provider_db_1``, ``provider_db_2``, …

Special id ``provider_failover`` tries all enabled admin endpoints in order.

No per-vendor Python modules. Pick provider + model in the UI → ``agent_model_catalog_owned_by``.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from typing import Any, Literal
import uuid

import httpx

from apps.backend.infrastructure.db import db
from apps.backend.infrastructure.llm_chat_attempt import make_llm_attempt
from apps.backend.infrastructure.llm_env_providers import (
    EnvLlmProviderRow,
    parse_llm_env_providers,
)

logger = logging.getLogger(__name__)

LlmStack = Literal["provider_env", "provider_db"]

PROVIDER_FAILOVER_ID = "provider_failover"
_LEGACY_DB_PROVIDER_OFFSET = 32

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
    max_parallel: int = 1
    source: str = "db"
    db_endpoint_id: int | None = None


def db_catalog_provider_id(endpoint_id: int) -> str:
    """Stable catalog id for an admin DB endpoint row."""
    return f"provider_db_{int(endpoint_id)}"


def parse_db_catalog_provider_id(provider_id: str) -> int | None:
    pid = (provider_id or "").strip().lower()
    if pid.startswith("provider_db_"):
        suffix = pid[len("provider_db_") :]
        return int(suffix) if suffix.isdigit() else None
    if pid.startswith("provider_"):
        suffix = pid[len("provider_") :]
        if suffix.isdigit() and int(suffix) > _LEGACY_DB_PROVIDER_OFFSET:
            return int(suffix) - _LEGACY_DB_PROVIDER_OFFSET
    return None


def normalize_catalog_provider_id(raw: Any) -> str | None:
    if raw is None:
        return None
    s = str(raw).strip().lower()
    t = "".join(c for c in s if c.isalnum() or c in "_-")[:64]
    return t or None


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
    raw = (model_from_resolution or "").strip()[:256]
    return raw


def _env_row_spec(row: EnvLlmProviderRow) -> CatalogProviderSpec:
    return CatalogProviderSpec(
        provider_id=row.provider_id,
        label=row.label,
        base_url=row.base_url,
        api_key=row.api_key,
        api_header_name=row.api_header_name,
        model_default=row.model_default,
        model_vlm=row.model_vlm,
        model_agent=row.model_agent,
        model_coding=row.model_coding,
        max_parallel=row.max_parallel,
        source=row.source,
    )


def _db_endpoint_spec(row: dict[str, Any]) -> CatalogProviderSpec:
    from apps.backend.infrastructure.operator_settings import normalize_external_llm_base_url

    eid = int(row["id"])
    bu = normalize_external_llm_base_url(_strip_opt(row.get("base_url"))) or ""
    header = _strip_opt(row.get("api_header_name")) or "Authorization"
    return CatalogProviderSpec(
        provider_id=db_catalog_provider_id(eid),
        label=(_strip_opt(row.get("label")) or f"LLM #{eid}")[:128],
        base_url=bu,
        api_key=_strip_opt(row.get("api_key")) or "",
        api_header_name=header,
        model_default=_strip_opt(row.get("model_default")),
        model_vlm=_strip_opt(row.get("model_vlm")),
        model_agent=_strip_opt(row.get("model_agent")),
        model_coding=_strip_opt(row.get("model_coding")),
        max_parallel=max(1, min(64, int(row.get("max_parallel") or 1))),
        source="db",
        db_endpoint_id=eid,
    )


def _provider_url_key(base_url: str) -> str:
    from apps.backend.infrastructure.operator_settings import normalize_external_llm_base_url

    return (normalize_external_llm_base_url(base_url) or base_url.rstrip("/")).lower()


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
    seen_urls: set[str] = set()

    try:
        db_rows = db.operator_provider_endpoints_list_all("chat")
        if not db_rows:
            db_rows = db.external_llm_endpoints_list_all()
    except RuntimeError:
        logger.debug("list_provider_specs: DB pool not ready — env providers only")
        db_rows = []
    for row in db_rows:
        sp = _db_endpoint_spec(row)
        if sp.provider_id in seen:
            continue
        if sp.base_url:
            specs.append(sp)
            seen.add(sp.provider_id)
            seen_urls.add(_provider_url_key(sp.base_url))

    for row in parse_llm_env_providers():
        sp = _env_row_spec(row)
        url_key = _provider_url_key(sp.base_url)
        if sp.provider_id not in seen and sp.base_url and url_key not in seen_urls:
            specs.append(sp)
            seen.add(sp.provider_id)
            seen_urls.add(url_key)

    _SPECS_CACHE = (now, specs)
    return list(specs)


def list_admin_llm_provider_rows() -> list[dict[str, Any]]:
    """Admin-facing LLM provider rows shared by LLM settings and benchmarks."""
    from apps.backend.infrastructure.operator_settings import normalize_external_llm_base_url

    db_enabled: dict[int, bool] = {}
    try:
        db_rows = db.operator_provider_endpoints_list_all("chat")
        if not db_rows:
            db_rows = db.external_llm_endpoints_list_all()
        for row in db_rows:
            db_enabled[int(row["id"])] = bool(row.get("enabled", True))
    except RuntimeError:
        pass

    seen_urls: set[str] = set()
    out: list[dict[str, Any]] = []
    for sp in list_provider_specs(force_refresh=True):
        base = (sp.base_url or "").strip()
        if not base:
            continue
        if sp.db_endpoint_id is not None and not db_enabled.get(sp.db_endpoint_id, True):
            continue
        url_key = (normalize_external_llm_base_url(base) or base).lower()
        if url_key in seen_urls:
            continue
        seen_urls.add(url_key)
        out.append(
            {
                "catalog_owned_by": sp.provider_id,
                "label": sp.label,
                "base_url": base,
                "source": sp.source,
                "endpoint_id": sp.db_endpoint_id,
                "model_default": sp.model_default,
                "model_vlm": sp.model_vlm,
                "model_agent": sp.model_agent,
                "model_coding": sp.model_coding,
            }
        )
    return out


def get_provider_spec(provider_id: str) -> CatalogProviderSpec | None:
    pid = normalize_catalog_provider_id(provider_id)
    if not pid:
        return None
    specs = list_provider_specs()
    for spec in specs:
        if spec.provider_id == pid:
            return spec
    legacy_db_id = parse_db_catalog_provider_id(pid)
    if legacy_db_id is not None:
        db_pid = db_catalog_provider_id(legacy_db_id)
        for spec in specs:
            if spec.provider_id == db_pid:
                return spec
    for row in parse_llm_env_providers():
        if normalize_catalog_provider_id(row.provider_id) != pid:
            continue
        env_url_key = _provider_url_key(row.base_url)
        for spec in specs:
            if _provider_url_key(spec.base_url) == env_url_key:
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


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, str):
            continue
        s = item.strip().lower()
        if not s or s in seen:
            continue
        out.append(s[:32])
        seen.add(s)
    return out


def _model_capabilities_from_item(item: dict[str, Any]) -> dict[str, Any]:
    arch = item.get("architecture")
    input_modalities: list[str] = []
    output_modalities: list[str] = []
    if isinstance(arch, dict):
        input_modalities = _string_list(arch.get("input_modalities"))
        output_modalities = _string_list(arch.get("output_modalities"))

    # OpenAI-compatible chat catalogs rarely expose modality metadata. For chat model
    # rows, text is the conservative default; richer servers can override via architecture.
    if not input_modalities:
        input_modalities = ["text"]
    if not output_modalities:
        output_modalities = ["text"]

    return {
        "input_modalities": input_modalities,
        "output_modalities": output_modalities,
    }


def _parse_models_payload(data: dict[str, Any], owned_by: str) -> list[dict[str, Any]]:
    from apps.backend.infrastructure.context_budget import extract_context_length_from_model_item

    out: list[dict[str, Any]] = []
    for item in data.get("data") or []:
        if not isinstance(item, dict):
            continue
        mid = item.get("id")
        if not isinstance(mid, str) or not mid.strip():
            continue
        row: dict[str, Any] = {
            "id": mid.strip(),
            "object": item.get("object") if isinstance(item.get("object"), str) else "model",
            "owned_by": owned_by,
        }
        ctx = extract_context_length_from_model_item(item)
        if ctx:
            row["context_length"] = ctx
        row["capabilities"] = _model_capabilities_from_item(item)
        out.append(row)
    return out


def fetch_full_model_catalog(
    *,
    tenant_id: int | None = None,
    user_id: uuid.UUID | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    return fetch_full_model_catalog_for_scope(
        include_hidden=False,
        tenant_id=tenant_id,
        user_id=user_id,
    )


def fetch_full_model_catalog_for_scope(
    *,
    include_hidden: bool = False,
    tenant_id: int | None = None,
    user_id: uuid.UUID | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
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
    if include_hidden:
        return merged, agentlayer
    if tenant_id is not None and user_id is not None:
        from apps.backend.infrastructure.model_access_policy import filter_catalog_rows_for_user

        return filter_catalog_rows_for_user(merged, tenant_id=tenant_id, user_id=user_id), agentlayer
    return _filter_chat_visible_models(merged), agentlayer


def _filter_chat_visible_models(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    try:
        visible = db.model_catalog_visible_index()
    except RuntimeError:
        return rows
    out: list[dict[str, Any]] = []
    for row in rows:
        provider_id = normalize_catalog_provider_id(row.get("owned_by"))
        model_id = str(row.get("id") or "").strip()
        if not provider_id or not model_id:
            continue
        if visible.get((provider_id, model_id), True):
            out.append(row)
    return out


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


def lookup_model_context_length(model_id: str, catalog_owned_by: str) -> int | None:
    """Context window for ``model_id`` on a specific catalog provider."""
    mid = (model_id or "").strip()
    ob = normalize_catalog_provider_id(catalog_owned_by)
    if not mid or not ob:
        return None

    # Prefer a direct GET /v1/models on the routed provider (llama.cpp meta.n_ctx, …).
    spec = get_provider_spec(ob)
    if spec is not None:
        rows, meta = fetch_models_for_provider(spec)
        if meta.get("reachable"):
            for row in rows:
                if str(row.get("id") or "").strip() != mid:
                    continue
                n = row.get("context_length")
                if isinstance(n, int) and n > 0:
                    return n
        else:
            logger.debug(
                "lookup_model_context_length: provider %s unreachable (%s)",
                ob,
                meta.get("detail"),
            )

    for row in fetch_full_model_catalog()[0]:
        if str(row.get("id") or "").strip() != mid:
            continue
        if normalize_catalog_provider_id(row.get("owned_by")) != ob:
            continue
        n = row.get("context_length")
        if isinstance(n, int) and n > 0:
            return n
    return None


def route_chat_by_catalog_provider(
    catalog_owned_by: str,
    model_from_resolution: str,
    profile_key: str,
    is_override: bool,
) -> tuple[list[tuple[str, dict[str, str], str, str]], LlmStack]:
    pid = normalize_catalog_provider_id(catalog_owned_by)
    if not pid:
        raise ValueError("Invalid catalog provider id.")

    if pid == PROVIDER_FAILOVER_ID:
        from apps.backend.infrastructure.operator_settings import _admin_llm_chat_attempts

        attempts = _admin_llm_chat_attempts(profile_key, is_override, model_from_resolution)
        if not attempts:
            raise ValueError(
                "provider_failover has no admin LLM endpoints — add endpoints under Admin → Interfaces "
                "or pick a specific provider id (provider_db_1, …)."
            )
        return attempts, "provider_db"

    spec = get_provider_spec(pid)
    if spec is None:
        raise ValueError(
            f"Unknown catalog provider {catalog_owned_by!r}. "
            "Add LLM_PROVIDER_N_* in .env or endpoints under Admin → Interfaces → LLM-Endpoints."
        )

    if not spec.base_url.strip():
        raise ValueError(f"Provider {pid!r} has no base URL configured.")

    chat_url = _chat_completions_url(spec)
    headers = provider_request_headers(spec)
    model = resolve_model_for_provider(spec, profile_key, is_override, model_from_resolution)
    if not model:
        raise ValueError(f"Provider {pid!r} has no model id for this request.")

    try:
        from apps.backend.domain.identity import get_identity
        from apps.backend.infrastructure.model_access_policy import is_model_allowed

        tenant_id, user_id = get_identity()
        if user_id is not None and not is_model_allowed(
            pid,
            model,
            tenant_id=tenant_id,
            user_id=user_id,
        ):
            raise ValueError(f"Model {model!r} is not available for provider {pid!r}.")
    except RuntimeError:
        pass

    logger.info(
        "catalog_route: provider=%s (%s) url=%s model=%r",
        pid,
        spec.source,
        chat_url,
        model,
    )
    stack: LlmStack = "provider_db" if spec.source == "db" else "provider_env"
    return [make_llm_attempt(chat_url, headers, model, pid)], stack


def first_env_provider_id() -> str | None:
    rows = parse_llm_env_providers()
    return rows[0].provider_id if rows else None


def first_admin_provider_id() -> str | None:
    rows = db.operator_provider_endpoints_list_all("chat")
    if not rows:
        rows = db.external_llm_endpoints_list_all()
    for row in rows:
        if _strip_opt(row.get("base_url")):
            return db_catalog_provider_id(int(row["id"]))
    return None

def invalidate_provider_specs_cache() -> None:
    global _SPECS_CACHE
    _SPECS_CACHE = None
