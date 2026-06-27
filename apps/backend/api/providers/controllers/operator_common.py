from __future__ import annotations

import asyncio
import uuid
from typing import Any, Literal

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field

from apps.backend.application.providers.use_cases.provider_admin_acl import (
    http_get_json,
    invalidate_provider_caches,
    list_operator_provider_endpoints,
    model_access_payload_for_scope,
    normalize_external_llm_base_url,
    parse_embedding_env_providers,
    parse_extractor_env_providers,
    parse_llm_env_providers,
    parse_voice_stt_env_providers,
    parse_voice_tts_env_providers,
    sync_model_access_payload,
)

class ExternalLlmModelsBody(BaseModel):
    """Optional form overrides; omitted fields use first endpoint or legacy operator_settings."""

    model_config = ConfigDict(extra="forbid")

    base_url: str | None = None
    api_key: str | None = None
    endpoint_id: int | None = Field(
        default=None,
        description="Use this endpoint's URL+key when base_url/api_key not sent.",
    )


class ExternalLlmEndpointItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int | None = None
    sort_order: int = 0
    enabled: bool = True
    label: str = ""
    base_url: str = ""
    api_key: str | None = None
    api_header_name: str | None = Field(
        default=None,
        description="HTTP header for api_key (Authorization, X-API-KEY, …). Default Authorization.",
    )
    model_default: str | None = None
    model_vlm: str | None = None
    model_agent: str | None = None
    model_coding: str | None = None
    max_parallel: int = Field(default=1, ge=1, le=64)


class ExternalLlmEndpointsPutBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    endpoints: list[ExternalLlmEndpointItem] = Field(default_factory=list)


class EnvLlmProvidersImportBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider_indexes: list[int] | None = Field(
        default=None,
        description="Env provider slots to import. Omit/null imports all detected slots.",
    )


class ModelCatalogPrefItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider_id: str = Field(min_length=1, max_length=64)
    model_id: str = Field(min_length=1, max_length=512)
    visible_in_chat: bool = True
    profile_tags: list[str] = Field(default_factory=list)
    sort_order: int = 0


class ModelCatalogPrefsPutBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prefs: list[ModelCatalogPrefItem] = Field(default_factory=list)


class ModelAccessPolicyItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider_id: str = Field(min_length=1, max_length=64)
    model_id: str = Field(min_length=1, max_length=512)
    access_state: Literal["inherit", "allow", "deny"] = "inherit"
    sort_order: int = 0


class ModelDefaultPolicyItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile: Literal["default", "agent", "coding", "vlm", "embedding", "extractor", "stt", "tts"]
    provider_id: str = Field(min_length=1, max_length=64)
    model_id: str = Field(min_length=1, max_length=512)


class ProviderCapabilityPolicyItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    capability: Literal["chat", "embedding", "extractor", "stt", "tts", "voice_realtime"]
    provider_id: str = Field(min_length=1, max_length=64)
    access_state: Literal["inherit", "allow", "deny"] = "inherit"


class ModelAccessPoliciesPutBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model_access: list[ModelAccessPolicyItem] = Field(default_factory=list)
    model_defaults: list[ModelDefaultPolicyItem] = Field(default_factory=list)
    provider_capabilities: list[ProviderCapabilityPolicyItem] = Field(default_factory=list)


class OperatorProviderEndpointItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int | None = None
    sort_order: int = 0
    enabled: bool = True
    label: str = ""
    base_url: str = ""
    api_key: str | None = None
    api_header_name: str | None = None
    model_default: str | None = None
    max_parallel: int = Field(default=1, ge=1, le=64)
    options_json: dict[str, Any] = Field(default_factory=dict)


class OperatorProviderEndpointsPutBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    endpoints: list[OperatorProviderEndpointItem] = Field(default_factory=list)
    delete_endpoint_ids: list[int] = Field(default_factory=list)


def _operator_provider_kind_or_404(kind: str) -> str:
    k = (kind or "").strip().lower()
    if k not in _operator_provider_endpoint_kinds():
        raise HTTPException(status_code=404, detail="Unknown provider endpoint kind.")
    return k


def _operator_endpoint_provider_id(kind: str, endpoint_id: int) -> str:
    if kind == "chat":
        return f"provider_db_{int(endpoint_id)}"
    return f"{kind}_provider_db_{int(endpoint_id)}"


def _operator_provider_endpoint_kinds() -> tuple[str, ...]:
    return ("chat", "embedding", "extractor", "voice_stt", "voice_tts")


def _operator_provider_endpoint_metadata() -> tuple[dict[str, Any], ...]:
    return (
        {
            "kind": "chat",
            "capability": "chat",
            "title_i18n_key": "modelAccessChatTitle",
            "intro_i18n_key": "modelAccessChatIntro",
            "empty_i18n_key": "modelAccessChatEmpty",
            "model_label_i18n_key": "ifMemModelId",
            "model_placeholder_i18n_key": "ifLlmSelectProviderModel",
            "model_setting_key": "chat_model",
            "env_prefix_pattern": "LLM_PROVIDER_N_*",
            "supports_models": True,
        },
        {
            "kind": "embedding",
            "capability": "embedding",
            "title_i18n_key": "modelAccessEmbeddingTitle",
            "intro_i18n_key": "modelAccessEmbeddingIntro",
            "empty_i18n_key": "modelAccessEmbeddingEmpty",
            "model_label_i18n_key": "ifMemModelId",
            "model_placeholder_i18n_key": "ifMemoryModelFilePlaceholder",
            "model_setting_key": "rag_embedding_model",
            "env_prefix_pattern": "EMBEDDING_PROVIDER_N_*",
            "supports_models": True,
        },
        {
            "kind": "extractor",
            "capability": "extractor",
            "title_i18n_key": "modelAccessExtractorTitle",
            "intro_i18n_key": "modelAccessExtractorIntro",
            "empty_i18n_key": "modelAccessExtractorEmpty",
            "model_label_i18n_key": "ifMemExtractorModel",
            "model_placeholder_i18n_key": "ifMemExtractorModelPlaceholder",
            "model_setting_key": "extractor_model",
            "env_prefix_pattern": "EXTRACTOR_PROVIDER_N_*",
            "supports_models": True,
        },
        {
            "kind": "voice_stt",
            "capability": "stt",
            "title_i18n_key": "modelAccessSttTitle",
            "intro_i18n_key": "modelAccessSttIntro",
            "empty_i18n_key": "modelAccessSttEmpty",
            "model_label_i18n_key": "ifPlatformVoiceSttModel",
            "model_placeholder_i18n_key": "ifLlmSelectProviderModel",
            "model_setting_key": "voice_stt_model",
            "env_prefix_pattern": "VOICE_STT_PROVIDER_N_*",
            "supports_models": True,
        },
        {
            "kind": "voice_tts",
            "capability": "tts",
            "title_i18n_key": "modelAccessTtsTitle",
            "intro_i18n_key": "modelAccessTtsIntro",
            "empty_i18n_key": "modelAccessTtsEmpty",
            "model_label_i18n_key": "ifPlatformVoiceTtsModel",
            "model_placeholder_i18n_key": "ifLlmSelectProviderModel",
            "model_setting_key": "voice_tts_model",
            "env_prefix_pattern": "VOICE_TTS_PROVIDER_N_*",
            "supports_models": True,
        },
    )


def _model_default_profile_metadata() -> tuple[dict[str, Any], ...]:
    return (
        {
            "profile": "default",
            "capability": "chat",
            "title_i18n_key": "modelAccessDefault_default",
            "source": "catalog",
        },
        {
            "profile": "agent",
            "capability": "chat",
            "title_i18n_key": "modelAccessDefault_agent",
            "source": "catalog",
        },
        {
            "profile": "coding",
            "capability": "chat",
            "title_i18n_key": "modelAccessDefault_coding",
            "source": "catalog",
        },
        {
            "profile": "vlm",
            "capability": "chat",
            "title_i18n_key": "modelAccessDefault_vlm",
            "source": "catalog",
        },
        {
            "profile": "embedding",
            "capability": "embedding",
            "title_i18n_key": "modelAccessDefault_embedding",
            "source": "provider_models",
        },
        {
            "profile": "extractor",
            "capability": "extractor",
            "title_i18n_key": "modelAccessDefault_extractor",
            "source": "provider_models",
        },
        {
            "profile": "stt",
            "capability": "stt",
            "title_i18n_key": "modelAccessDefault_stt",
            "source": "provider_models",
        },
        {
            "profile": "tts",
            "capability": "tts",
            "title_i18n_key": "modelAccessDefault_tts",
            "source": "provider_models",
        },
    )


def _invalidate_non_llm_provider_caches(kind: str) -> None:
    invalidate_provider_caches(kind)
def _env_llm_cleanup_keys(index: int) -> list[str]:
    prefix = f"LLM_PROVIDER_{int(index)}"
    return [
        f"{prefix}_BASE_URL",
        f"{prefix}_LABEL",
        f"{prefix}_API_KEY",
        f"{prefix}_API_HEADER_NAME",
        f"{prefix}_MODEL_DEFAULT",
        f"{prefix}_MODEL_VLM",
        f"{prefix}_MODEL_AGENT",
        f"{prefix}_MODEL_CODING",
        f"{prefix}_MAX_PARALLEL",
    ]


def _external_llm_endpoint_public_id(row: dict[str, Any]) -> int | None:
    try:
        return int(row.get("id")) if row.get("id") is not None else None
    except (TypeError, ValueError):
        return None


def _env_llm_provider_preview_rows() -> list[dict[str, Any]]:
    return _operator_env_provider_preview_rows("chat")
def _model_access_payload_for_scope(scope: str, tenant_id: int | None = None, user_id: uuid.UUID | None = None) -> dict[str, Any]:
    return model_access_payload_for_scope(scope=scope, tenant_id=tenant_id, user_id=user_id)


def _sync_model_access_payload(
    scope: str,
    body: ModelAccessPoliciesPutBody,
    *,
    tenant_id: int | None = None,
    user_id: uuid.UUID | None = None,
) -> None:
    sync_model_access_payload(
        scope,
        [x.model_dump() for x in body.model_access],
        [x.model_dump() for x in body.model_defaults],
        [x.model_dump() for x in body.provider_capabilities],
        tenant_id=tenant_id,
        user_id=user_id,
    )
def _operator_env_prefix(kind: str, index: int) -> str:
    if kind == "chat":
        return f"LLM_PROVIDER_{int(index)}"
    if kind == "embedding":
        return f"EMBEDDING_PROVIDER_{int(index)}"
    if kind == "extractor":
        return f"EXTRACTOR_PROVIDER_{int(index)}"
    if kind == "voice_stt":
        return f"VOICE_STT_PROVIDER_{int(index)}"
    if kind == "voice_tts":
        return f"VOICE_TTS_PROVIDER_{int(index)}"
    raise HTTPException(status_code=404, detail="Unknown provider endpoint kind.")


def _operator_env_cleanup_keys(kind: str, index: int) -> list[str]:
    prefix = _operator_env_prefix(kind, index)
    if kind == "chat":
        suffixes = [
            "BASE_URL",
            "LABEL",
            "API_KEY",
            "API_HEADER_NAME",
            "MODEL_DEFAULT",
            "MODEL_VLM",
            "MODEL_AGENT",
            "MODEL_CODING",
            "MAX_PARALLEL",
        ]
    elif kind == "embedding":
        suffixes = ["BASE_URL", "LABEL", "API_KEY", "API_HEADER_NAME", "MODEL_DEFAULT"]
    elif kind == "extractor":
        suffixes = ["BASE_URL", "NAME", "LABEL", "API_KEY", "API_HEADER_NAME", "MODEL", "TIMEOUT_SEC"]
    elif kind == "voice_stt":
        suffixes = [
            "BASE_URL",
            "LABEL",
            "API_KEY",
            "API_HEADER_NAME",
            "MODEL",
            "MODEL_STT",
            "API_STYLE",
            "STT_API_STYLE",
            "TRANSCRIBE_PATH",
            "STT_PATH",
        ]
    elif kind == "voice_tts":
        suffixes = [
            "BASE_URL",
            "LABEL",
            "API_KEY",
            "API_HEADER_NAME",
            "MODEL",
            "MODEL_TTS",
            "MODEL_TTS_VOICE",
            "VOICE",
        ]
    else:
        suffixes = []
    return [f"{prefix}_{s}" for s in suffixes]


def _operator_env_rows_for_kind(kind: str):
    if kind == "chat":
        return parse_llm_env_providers()
    if kind == "embedding":
        return parse_embedding_env_providers()
    if kind == "extractor":
        return parse_extractor_env_providers()
    if kind == "voice_stt":
        return parse_voice_stt_env_providers()
    if kind == "voice_tts":
        return parse_voice_tts_env_providers()
    raise HTTPException(status_code=404, detail="Unknown provider endpoint kind.")


def _operator_env_options(kind: str, row: Any) -> dict[str, Any]:
    if kind == "extractor":
        return {"timeout_sec": float(getattr(row, "timeout_sec", 120.0))}
    if kind == "voice_stt":
        return {
            "stt_api_style": getattr(row, "stt_api_style", "openai"),
            "stt_transcribe_path": getattr(row, "stt_transcribe_path", None),
        }
    if kind == "voice_tts":
        return {"model_tts_voice": getattr(row, "model_tts_voice", None)}
    return {}


def _operator_env_model(kind: str, row: Any) -> str | None:
    if kind in {"voice_stt", "voice_tts"}:
        return str(getattr(row, "model", "") or "").strip() or None
    return str(getattr(row, "model_default", "") or "").strip() or None


def _operator_provider_endpoint_public_id(row: dict[str, Any]) -> int | None:
    try:
        return int(row.get("id")) if row.get("id") is not None else None
    except (TypeError, ValueError):
        return None


def _operator_provider_base_url(raw: Any) -> str:
    """Preserve the configured OpenAI-compatible base path for non-chat providers."""
    return str(raw or "").strip().strip("'\"").rstrip("/")


def _operator_provider_dedupe_key(raw: Any) -> str:
    """Compare equivalent OpenAI-compatible bases without changing what we store/display."""
    base = _operator_provider_base_url(raw)
    return (normalize_external_llm_base_url(base) or base).lower()


def _operator_env_provider_preview_rows(kind: str) -> list[dict[str, Any]]:
    kind_v = _operator_provider_kind_or_404(kind)
    db_rows = list_operator_provider_endpoints(kind_v)
    db_by_base: dict[str, dict[str, Any]] = {}
    for row in db_rows:
        key = _operator_provider_dedupe_key(row.get("base_url"))
        if key:
            db_by_base.setdefault(key, row)

    out: list[dict[str, Any]] = []
    for row in _operator_env_rows_for_kind(kind_v):
        base = _operator_provider_base_url(row.base_url)
        match = db_by_base.get(_operator_provider_dedupe_key(base))
        key = str(getattr(row, "api_key", "") or "")
        out.append(
            {
                "kind": kind_v,
                "index": int(getattr(row, "index")),
                "provider_id": getattr(row, "provider_id"),
                "label": getattr(row, "label"),
                "base_url": base,
                "api_key_configured": bool(key.strip()),
                "api_key_last4": key[-4:] if len(key) >= 4 else None,
                "api_header_name": getattr(row, "api_header_name", None) or "Authorization",
                "model_default": _operator_env_model(kind_v, row),
                "max_parallel": int(getattr(row, "max_parallel", 1) or 1),
                "options_json": _operator_env_options(kind_v, row),
                "cleanup_keys": _operator_env_cleanup_keys(kind_v, int(getattr(row, "index"))),
                "already_in_db": match is not None,
                "matched_db_endpoint_id": _operator_provider_endpoint_public_id(match or {}),
            }
        )
    return out


__all__ = [name for name in globals() if not name.startswith("__")]
def _provider_models_url(base_url: str) -> str:
    base = _operator_provider_base_url(base_url)
    low = base.lower()
    if low.endswith("/models"):
        return base
    if low.endswith("/v1"):
        return f"{base}/models"
    return f"{base}/v1/models"


def _provider_auth_headers(api_key: str, api_header_name: str) -> dict[str, str]:
    key = (api_key or "").strip()
    if not key:
        return {}
    header = (api_header_name or "Authorization").strip() or "Authorization"
    if header.lower() == "authorization":
        return {"Authorization": key if key.lower().startswith("bearer ") else f"Bearer {key}"}
    return {header: key}


def _provider_configured_model_rows(spec: Any) -> list[dict[str, str]]:
    ids: list[str] = []
    for attr in ("model_default", "model", "model_stt", "model_tts"):
        value = str(getattr(spec, attr, "") or "").strip()
        if value and value not in ids:
            ids.append(value)
    return [{"id": model_id} for model_id in ids]
