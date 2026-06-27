"""Application anti-corruption adapters for provider admin use cases."""
from __future__ import annotations

import json
import uuid
from typing import Any

import httpx
from fastapi import HTTPException

from apps.backend.infrastructure.agent_runtime.llm_env_providers import parse_llm_env_providers
from apps.backend.infrastructure.db import db
from apps.backend.infrastructure.identity.auth import get_user_by_id, require_admin
from apps.backend.infrastructure.providers.embedding_env_providers import parse_embedding_env_providers
from apps.backend.infrastructure.providers.extractor_env_providers import parse_extractor_env_providers
from apps.backend.infrastructure.providers.openai_compat_http import http_get_json
from apps.backend.infrastructure.settings.operator_settings import (
    InterfaceHintsPayload,
    OperatorSettingsPatch,
    OperatorSettingsPayload,
    apply_interface_hints,
    apply_operator_settings_patch,
    apply_update as apply_operator_settings_update,
    external_api_headers,
    external_models_list_url,
    interface_hints_public,
    invalidate_operator_settings_cache,
    normalize_external_llm_base_url,
    public_dict as operator_settings_public,
    resolve_external_llm_credentials_for_catalog,
)
from apps.backend.infrastructure.voice.voice_env_providers import (
    parse_voice_stt_env_providers,
    parse_voice_tts_env_providers,
)


async def require_provider_admin(request: Any) -> None:
    await require_admin(request)


def invalidate_provider_caches(kind: str) -> None:
    invalidate_operator_settings_cache()
    if kind == "chat":
        from apps.backend.infrastructure.providers.model_catalog_routing import invalidate_model_catalog_cache

        invalidate_model_catalog_cache()
    elif kind == "embedding":
        from apps.backend.infrastructure.providers.embedding_catalog_providers import (
            invalidate_embedding_provider_specs_cache,
        )

        invalidate_embedding_provider_specs_cache()
    elif kind in {"voice_stt", "voice_tts"}:
        from apps.backend.infrastructure.voice.voice_catalog_providers import (
            invalidate_voice_provider_specs_cache,
        )

        invalidate_voice_provider_specs_cache()
    elif kind == "extractor":
        from apps.backend.infrastructure.providers.extractor_catalog_providers import (
            invalidate_extractor_provider_specs_cache,
        )

        invalidate_extractor_provider_specs_cache()


def model_access_payload_for_scope(
    scope: str,
    tenant_id: int | None = None,
    user_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    from apps.backend.infrastructure.providers.model_access_policy import effective_policy_preview

    return effective_policy_preview(scope=scope, tenant_id=tenant_id, user_id=user_id)


def sync_model_access_payload(
    scope: str,
    model_access: list[dict[str, Any]],
    model_defaults: list[dict[str, Any]],
    provider_capabilities: list[dict[str, Any]],
    *,
    tenant_id: int | None = None,
    user_id: uuid.UUID | None = None,
) -> None:
    db.model_access_policies_sync(scope, model_access, tenant_id=tenant_id, user_id=user_id)
    db.model_default_policies_sync(scope, model_defaults, tenant_id=tenant_id, user_id=user_id)
    db.provider_capability_policies_sync(
        scope,
        provider_capabilities,
        tenant_id=tenant_id,
        user_id=user_id,
    )
    from apps.backend.infrastructure.providers.model_catalog_routing import invalidate_model_catalog_cache

    invalidate_model_catalog_cache()


def list_operator_provider_endpoints(kind: str) -> list[dict[str, Any]]:
    return db.operator_provider_endpoints_list_all(kind)


def sync_operator_provider_endpoints(
    kind: str,
    rows: list[dict[str, Any]],
    *,
    delete_missing: bool = False,
    delete_ids: list[int] | None = None,
) -> None:
    db.operator_provider_endpoints_sync(
        kind,
        rows,
        delete_missing=delete_missing,
        delete_ids=delete_ids,
    )


def list_model_catalog_with_prefs() -> tuple[list[dict[str, Any]], dict[str, Any], list[dict[str, Any]]]:
    from apps.backend.infrastructure.providers.model_catalog_providers import fetch_full_model_catalog_for_scope

    rows, agentlayer = fetch_full_model_catalog_for_scope(include_hidden=True)
    return rows, agentlayer, db.model_catalog_prefs_list_all()


def list_admin_llm_provider_rows() -> list[dict[str, Any]]:
    from apps.backend.infrastructure.providers.model_catalog_providers import list_admin_llm_provider_rows as _impl

    return _impl()


def sync_model_catalog_prefs(rows: list[dict[str, Any]]) -> None:
    db.model_catalog_prefs_sync(rows)
    from apps.backend.infrastructure.providers.model_catalog_routing import invalidate_model_catalog_cache

    invalidate_model_catalog_cache()


def tenant_exists(tenant_id: int) -> bool:
    return db.tenant_exists(tenant_id)


def user_exists(user_id: uuid.UUID) -> bool:
    return get_user_by_id(user_id) is not None


def tenant_id_for_user(user_id: uuid.UUID) -> int | None:
    return db.user_tenant_id(user_id)


def provider_models_url(base_url: str, normalize_base_url) -> str:
    base = normalize_base_url(base_url)
    low = base.lower()
    if low.endswith("/models"):
        return base
    if low.endswith("/v1"):
        return f"{base}/models"
    return f"{base}/v1/models"


def provider_auth_headers(api_key: str, api_header_name: str) -> dict[str, str]:
    key = (api_key or "").strip()
    if not key:
        return {}
    header = (api_header_name or "Authorization").strip() or "Authorization"
    if header.lower() == "authorization":
        return {"Authorization": key if key.lower().startswith("bearer ") else f"Bearer {key}"}
    return {header: key}


def provider_configured_model_rows(spec: Any) -> list[dict[str, str]]:
    ids: list[str] = []
    for attr in ("model_default", "model", "model_stt", "model_tts"):
        value = str(getattr(spec, attr, "") or "").strip()
        if value and value not in ids:
            ids.append(value)
    return [{"id": model_id} for model_id in ids]


def chat_provider_model_rows(provider_id: str | None = None) -> list[dict[str, str]]:
    from apps.backend.infrastructure.providers.model_catalog_providers import fetch_full_model_catalog_for_scope

    rows, _agentlayer = fetch_full_model_catalog_for_scope(include_hidden=True)
    pid = (provider_id or "").strip().lower()
    if pid.startswith("chat_provider_db_"):
        pid = "provider_db_" + pid[len("chat_provider_db_") :]
    return [
        {"id": str(row.get("id") or "").strip()}
        for row in rows
        if (not pid or str(row.get("owned_by") or "").strip().lower() == pid)
        and str(row.get("id") or "").strip()
    ]


def embedding_provider_model_rows(provider_id: str | None = None) -> tuple[list[dict[str, str]], Any]:
    from apps.backend.infrastructure.providers.embedding_client import fetch_embedding_models_list

    models, detail = fetch_embedding_models_list(provider_id=provider_id, timeout=12.0)
    return [{"id": m} for m in models], detail


def provider_spec_for_kind(kind: str, provider_id: str | None) -> Any:
    if kind == "extractor":
        from apps.backend.infrastructure.providers.extractor_catalog_providers import get_extractor_provider_spec

        return get_extractor_provider_spec(provider_id)
    if kind == "voice_stt":
        from apps.backend.infrastructure.voice.voice_catalog_providers import get_voice_stt_provider_spec

        return get_voice_stt_provider_spec(provider_id or "")
    if kind == "voice_tts":
        from apps.backend.infrastructure.voice.voice_catalog_providers import get_voice_tts_provider_spec

        return get_voice_tts_provider_spec(provider_id or "")
    raise HTTPException(status_code=404, detail="Provider not found.")


async def fetch_external_llm_models_payload(base_url: str, api_key: str) -> Any:
    url = external_models_list_url(base_url)
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                url,
                headers=external_api_headers(base_url, api_key),
                timeout=httpx.Timeout(45.0),
            )
    except httpx.RequestError as e:
        raise HTTPException(status_code=502, detail=f"Verbindung fehlgeschlagen: {e}") from e
    if resp.status_code != 200:
        snippet = (resp.text or "").strip()[:4000]
        raise HTTPException(
            status_code=min(resp.status_code, 599),
            detail=snippet or f"HTTP {resp.status_code}",
        )
    try:
        return resp.json()
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=502, detail="Antwort der API war kein JSON.") from e
