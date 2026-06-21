"""Voice STT/TTS provider catalogs (separate env chains + Admin DB)."""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from typing import Any, Literal

from apps.backend.infrastructure.voice_env_providers import (
    EnvVoiceProviderRow,
    SttApiStyle,
    VOICE_ENV_PROVIDER_MAX,
    VoiceRole,
    parse_voice_stt_env_providers,
    parse_voice_tts_env_providers,
    strip_env_value,
)
from apps.backend.infrastructure.db import db

logger = logging.getLogger(__name__)

_STT_CACHE: tuple[float, list[VoiceProviderSpec]] | None = None
_TTS_CACHE: tuple[float, list[VoiceProviderSpec]] | None = None
_CACHE_TTL_SEC = 2.0


@dataclass(frozen=True)
class VoiceProviderSpec:
    role: VoiceRole
    provider_id: str
    label: str
    base_url: str
    api_key: str
    api_header_name: str
    model_stt: str = "whisper-1"
    model_tts: str = "tts-1"
    model_tts_voice: str = "alloy"
    stt_api_style: SttApiStyle = "openai"
    stt_transcribe_path: str | None = None
    source: str = "env"


def normalize_voice_provider_id(raw: Any) -> str | None:
    if raw is None:
        return None
    s = str(raw).strip().lower()
    t = "".join(c for c in s if c.isalnum() or c in "_-")[:64]
    return t or None


def db_voice_provider_id(role: VoiceRole, endpoint_id: int) -> str:
    return f"voice_{role}_provider_{VOICE_ENV_PROVIDER_MAX + int(endpoint_id)}"


def parse_db_voice_provider_id(role: VoiceRole, provider_id: str) -> int | None:
    pid = (provider_id or "").strip().lower()
    prefix = f"voice_{role}_provider_"
    if not pid.startswith(prefix):
        return None
    suffix = pid[len(prefix) :]
    if not suffix.isdigit():
        return None
    slot = int(suffix)
    if slot <= VOICE_ENV_PROVIDER_MAX:
        return None
    return slot - VOICE_ENV_PROVIDER_MAX


def _env_row_spec(row: EnvVoiceProviderRow) -> VoiceProviderSpec:
    if row.role == "stt":
        return VoiceProviderSpec(
            role="stt",
            provider_id=row.provider_id,
            label=row.label,
            base_url=row.base_url,
            api_key=row.api_key,
            api_header_name=row.api_header_name,
            model_stt=row.model[:128],
            stt_api_style=row.stt_api_style,
            stt_transcribe_path=row.stt_transcribe_path,
            source=row.source,
        )
    return VoiceProviderSpec(
        role="tts",
        provider_id=row.provider_id,
        label=row.label,
        base_url=row.base_url,
        api_key=row.api_key,
        api_header_name=row.api_header_name,
        model_tts=row.model[:128],
        model_tts_voice=(row.model_tts_voice or "alloy")[:64],
        source=row.source,
    )


def _db_endpoint_spec(role: VoiceRole, row: dict[str, Any]) -> VoiceProviderSpec:
    eid = int(row["id"])
    options = row.get("options_json") if isinstance(row.get("options_json"), dict) else {}
    base = str(row.get("base_url") or "").strip().rstrip("/")
    label = (str(row.get("label") or "").strip() or f"Voice {role.upper()} #{eid}")[:128]
    model_default = str(row.get("model_default") or "").strip()
    if role == "stt":
        return VoiceProviderSpec(
            role="stt",
            provider_id=db_voice_provider_id("stt", eid),
            label=label,
            base_url=base,
            api_key=str(row.get("api_key") or "").strip(),
            api_header_name=str(row.get("api_header_name") or "").strip() or "Authorization",
            model_stt=(model_default or "whisper-1")[:128],
            stt_api_style=str(options.get("stt_api_style") or "openai")[:32],  # type: ignore[arg-type]
            stt_transcribe_path=(str(options.get("stt_transcribe_path") or "").strip() or None),
            source="db",
        )
    return VoiceProviderSpec(
        role="tts",
        provider_id=db_voice_provider_id("tts", eid),
        label=label,
        base_url=base,
        api_key=str(row.get("api_key") or "").strip(),
        api_header_name=str(row.get("api_header_name") or "").strip() or "Authorization",
        model_tts=(model_default or "tts-1")[:128],
        model_tts_voice=(str(options.get("voice") or "alloy").strip() or "alloy")[:64],
        source="db",
    )


def _list_role_specs(role: VoiceRole, *, force_refresh: bool = False) -> list[VoiceProviderSpec]:
    global _STT_CACHE, _TTS_CACHE
    now = time.monotonic()
    cache = _STT_CACHE if role == "stt" else _TTS_CACHE
    if not force_refresh and cache is not None and now - cache[0] <= _CACHE_TTL_SEC:
        return list(cache[1])

    parse_env = parse_voice_stt_env_providers if role == "stt" else parse_voice_tts_env_providers
    specs: list[VoiceProviderSpec] = []
    seen: set[str] = set()

    for row in parse_env():
        sp = _env_row_spec(row)
        if sp.provider_id not in seen and sp.base_url:
            specs.append(sp)
            seen.add(sp.provider_id)

    kind = "voice_stt" if role == "stt" else "voice_tts"
    try:
        db_rows = db.operator_provider_endpoints_list_all(kind)
    except RuntimeError:
        logger.debug("voice provider catalog: DB pool not ready — env providers only")
        db_rows = []
    for row in db_rows:
        if not row.get("enabled", True):
            continue
        sp = _db_endpoint_spec(role, row)
        if sp.provider_id not in seen and sp.base_url:
            specs.append(sp)
            seen.add(sp.provider_id)

    if role == "stt":
        _STT_CACHE = (now, specs)
    else:
        _TTS_CACHE = (now, specs)
    return list(specs)


def list_voice_stt_provider_specs(*, force_refresh: bool = False) -> list[VoiceProviderSpec]:
    return _list_role_specs("stt", force_refresh=force_refresh)


def list_voice_tts_provider_specs(*, force_refresh: bool = False) -> list[VoiceProviderSpec]:
    return _list_role_specs("tts", force_refresh=force_refresh)


def list_voice_provider_specs(*, force_refresh: bool = False) -> list[VoiceProviderSpec]:
    """Combined list for admin UI (each entry is STT or TTS by role)."""
    return list_voice_stt_provider_specs(force_refresh=force_refresh) + list_voice_tts_provider_specs(
        force_refresh=force_refresh
    )


def get_voice_stt_provider_spec(provider_id: str) -> VoiceProviderSpec | None:
    pid = normalize_voice_provider_id(provider_id)
    if not pid:
        return None
    for spec in list_voice_stt_provider_specs():
        if spec.provider_id == pid:
            return spec
    return None


def get_voice_tts_provider_spec(provider_id: str) -> VoiceProviderSpec | None:
    pid = normalize_voice_provider_id(provider_id)
    if not pid:
        return None
    for spec in list_voice_tts_provider_specs():
        if spec.provider_id == pid:
            return spec
    return None


def get_voice_provider_spec(provider_id: str) -> VoiceProviderSpec | None:
    return get_voice_stt_provider_spec(provider_id) or get_voice_tts_provider_spec(provider_id)


def _env_provider_id_override(key: str) -> str | None:
    raw = strip_env_value(os.environ.get(key))
    return normalize_voice_provider_id(raw) if raw else None


def _resolve_role_provider_id(role: VoiceRole) -> str | None:
    get_spec = get_voice_stt_provider_spec if role == "stt" else get_voice_tts_provider_spec
    list_specs = list_voice_stt_provider_specs if role == "stt" else list_voice_tts_provider_specs

    try:
        from apps.backend.domain.voice import voice_policy

        op = voice_policy.operator_voice_row()
        db_key = "voice_stt_provider_id" if role == "stt" else "voice_tts_provider_id"
        db_active = (str(op.get(db_key) or "").strip())
        if db_active and get_spec(db_active):
            return normalize_voice_provider_id(db_active)
    except Exception:
        pass

    env_key = "VOICE_STT_PROVIDER_ID" if role == "stt" else "VOICE_TTS_PROVIDER_ID"
    env_pid = _env_provider_id_override(env_key)
    if env_pid and get_spec(env_pid):
        return env_pid

    specs = list_specs()
    if specs:
        return specs[0].provider_id
    return None


def resolve_active_voice_stt_provider_id() -> str | None:
    return _resolve_role_provider_id("stt")


def resolve_active_voice_tts_provider_id() -> str | None:
    return _resolve_role_provider_id("tts")


def resolve_active_voice_stt_spec() -> VoiceProviderSpec | None:
    pid = resolve_active_voice_stt_provider_id()
    if not pid:
        return None
    return get_voice_stt_provider_spec(pid)


def resolve_active_voice_tts_spec() -> VoiceProviderSpec | None:
    pid = resolve_active_voice_tts_provider_id()
    if not pid:
        return None
    return get_voice_tts_provider_spec(pid)


def resolve_active_voice_provider_id() -> str | None:
    return resolve_active_voice_stt_provider_id()


def resolve_active_voice_spec() -> VoiceProviderSpec | None:
    return resolve_active_voice_stt_spec()


def voice_auth_headers(spec: VoiceProviderSpec) -> dict[str, str]:
    hn = (spec.api_header_name or "Authorization").strip() or "Authorization"
    key = (spec.api_key or "").strip()
    if hn.lower() == "authorization":
        return {"Authorization": f"Bearer {key}"} if key else {}
    return {hn: key} if key else {}


def voice_role_configured(role: VoiceRole) -> bool:
    spec = resolve_active_voice_stt_spec() if role == "stt" else resolve_active_voice_tts_spec()
    return bool(spec and spec.base_url and (spec.api_key or "").strip())


def invalidate_voice_provider_specs_cache() -> None:
    global _STT_CACHE, _TTS_CACHE
    _STT_CACHE = None
    _TTS_CACHE = None
