"""Operator voice settings — separate UPDATE (media pattern)."""

from __future__ import annotations

from typing import Any, Protocol

from apps.backend.domain.voice import voice_policy


class OperatorVoiceSettingsDependencies(Protocol):
    def list_voice_stt_provider_specs(self) -> list[Any]: ...

    def list_voice_tts_provider_specs(self) -> list[Any]: ...

    def resolve_active_voice_stt_spec(self) -> Any | None: ...

    def resolve_active_voice_tts_spec(self) -> Any | None: ...

    def resolve_active_voice_stt_provider_id(self) -> str | None: ...

    def resolve_active_voice_tts_provider_id(self) -> str | None: ...

    def voice_role_configured(self, role: str) -> bool: ...

    def apply_voice_operator_row(self, out: dict[str, Any]) -> None: ...

    def invalidate_operator_settings(self) -> None: ...

    def sync_single_provider_endpoint(self, role: str, **kwargs: Any) -> None: ...

    def invalidate_voice_provider_specs_cache(self) -> None: ...


_deps: OperatorVoiceSettingsDependencies | None = None


def register_operator_voice_settings_dependencies(deps: OperatorVoiceSettingsDependencies) -> None:
    global _deps
    _deps = deps


def _require_deps() -> OperatorVoiceSettingsDependencies:
    if _deps is None:
        raise RuntimeError("operator voice settings dependencies not registered")
    return _deps


def list_voice_stt_provider_specs() -> list[Any]:
    return _deps.list_voice_stt_provider_specs() if _deps is not None else []


def list_voice_tts_provider_specs() -> list[Any]:
    return _deps.list_voice_tts_provider_specs() if _deps is not None else []


def resolve_active_voice_stt_spec() -> Any | None:
    return _deps.resolve_active_voice_stt_spec() if _deps is not None else None


def resolve_active_voice_tts_spec() -> Any | None:
    return _deps.resolve_active_voice_tts_spec() if _deps is not None else None


def resolve_active_voice_stt_provider_id() -> str | None:
    return _deps.resolve_active_voice_stt_provider_id() if _deps is not None else None


def resolve_active_voice_tts_provider_id() -> str | None:
    return _deps.resolve_active_voice_tts_provider_id() if _deps is not None else None


def voice_role_configured(role: str) -> bool:
    return bool(_deps and _deps.voice_role_configured(role))


def _provider_public_rows(specs: list) -> list[dict[str, str]]:
    return [
        {
            "provider_id": s.provider_id,
            "label": s.label,
            "source": s.source,
            "base_url": s.base_url,
            "role": s.role,
        }
        for s in specs
    ]


def voice_settings_public_fields() -> dict[str, Any]:
    op = voice_policy.operator_voice_row()
    stt_specs = list_voice_stt_provider_specs()
    tts_specs = list_voice_tts_provider_specs()
    stt_spec = resolve_active_voice_stt_spec()
    tts_spec = resolve_active_voice_tts_spec()
    stt_id = resolve_active_voice_stt_provider_id()
    tts_id = resolve_active_voice_tts_provider_id()
    db_stored = (str(op.get("voice_api_base_url") or "").strip() or None)
    env_stt = [s for s in stt_specs if s.source.startswith("env")]
    env_tts = [s for s in tts_specs if s.source.startswith("env")]
    base_source: str | None = (
        "env" if env_stt or env_tts else ("operator_settings" if db_stored else None)
    )

    return {
        "voice_enabled": bool(op.get("voice_enabled")),
        "voice_api_base_url": db_stored,
        "voice_api_base_source": base_source,
        "voice_api_key_configured": voice_role_configured("stt") or voice_role_configured("tts"),
        "voice_stt_provider_id": (str(op.get("voice_stt_provider_id") or "").strip() or None),
        "voice_stt_provider_id_effective": stt_id,
        "voice_stt_provider_id_source": "operator_settings" if op.get("voice_stt_provider_id") else None,
        "voice_tts_provider_id": (str(op.get("voice_tts_provider_id") or "").strip() or None),
        "voice_tts_provider_id_effective": tts_id,
        "voice_tts_provider_id_source": "operator_settings" if op.get("voice_tts_provider_id") else None,
        "voice_stt_api_base_effective": (stt_spec.base_url.rstrip("/") if stt_spec else None),
        "voice_tts_api_base_effective": (tts_spec.base_url.rstrip("/") if tts_spec else None),
        "voice_stt_providers": _provider_public_rows(stt_specs),
        "voice_tts_providers": _provider_public_rows(tts_specs),
        "voice_providers": _provider_public_rows(stt_specs + tts_specs),
        "voice_stt_model": voice_policy.voice_stt_model(),
        "voice_tts_model": voice_policy.voice_tts_model(),
        "voice_tts_voice": (str(op.get("voice_tts_voice") or "").strip() or "alloy"),
        "voice_max_seconds": int(op.get("voice_max_seconds") or 120),
        "voice_max_bytes": int(op.get("voice_max_bytes") or 10_485_760),
        "voice_bridge_telegram": bool(op.get("voice_bridge_telegram", True)),
        "voice_bridge_discord": bool(op.get("voice_bridge_discord", True)),
        "voice_realtime_enabled": bool(op.get("voice_realtime_enabled")),
        "voice_discord_vc_enabled": bool(op.get("voice_discord_vc_enabled")),
    }


def apply_voice_operator_patch(patch: dict[str, Any]) -> None:
    keys = (
        "voice_enabled",
        "voice_provider_id",
        "voice_stt_provider_id",
        "voice_tts_provider_id",
        "voice_api_base_url",
        "voice_api_key",
        "voice_stt_model",
        "voice_tts_model",
        "voice_tts_voice",
        "voice_max_seconds",
        "voice_max_bytes",
        "voice_bridge_telegram",
        "voice_bridge_discord",
        "voice_realtime_enabled",
        "voice_discord_vc_enabled",
    )
    if not any(k in patch for k in keys):
        return

    cur = voice_policy.operator_voice_row()
    out = dict(cur)

    if "voice_enabled" in patch:
        out["voice_enabled"] = bool(patch["voice_enabled"])
    if "voice_provider_id" in patch:
        v = patch["voice_provider_id"]
        out["voice_provider_id"] = None if v is None else (str(v).strip()[:64] or None)
    if "voice_stt_provider_id" in patch:
        v = patch["voice_stt_provider_id"]
        out["voice_stt_provider_id"] = None if v is None else (str(v).strip()[:64] or None)
    if "voice_tts_provider_id" in patch:
        v = patch["voice_tts_provider_id"]
        out["voice_tts_provider_id"] = None if v is None else (str(v).strip()[:64] or None)
    if "voice_api_base_url" in patch:
        v = patch["voice_api_base_url"]
        out["voice_api_base_url"] = None if v is None else (str(v).strip().rstrip("/") or None)
    if "voice_api_key" in patch:
        v = patch["voice_api_key"]
        if v is None:
            out["voice_api_key"] = None
        else:
            s = str(v).strip()
            out["voice_api_key"] = s or None
    if "voice_stt_model" in patch:
        v = patch["voice_stt_model"]
        out["voice_stt_model"] = None if v is None else (str(v).strip()[:128] or None)
    if "voice_tts_model" in patch:
        v = patch["voice_tts_model"]
        out["voice_tts_model"] = None if v is None else (str(v).strip()[:128] or None)
    if "voice_tts_voice" in patch:
        v = patch["voice_tts_voice"]
        out["voice_tts_voice"] = None if v is None else (str(v).strip()[:64] or None)
    if "voice_max_seconds" in patch:
        v = patch["voice_max_seconds"]
        if v is None:
            out["voice_max_seconds"] = None
        else:
            try:
                out["voice_max_seconds"] = max(5, min(int(v), 600))
            except (TypeError, ValueError):
                out["voice_max_seconds"] = 120
    if "voice_max_bytes" in patch:
        v = patch["voice_max_bytes"]
        if v is None:
            out["voice_max_bytes"] = None
        else:
            try:
                out["voice_max_bytes"] = max(64_000, min(int(v), 52_428_800))
            except (TypeError, ValueError):
                out["voice_max_bytes"] = 10_485_760
    if "voice_bridge_telegram" in patch:
        out["voice_bridge_telegram"] = bool(patch["voice_bridge_telegram"])
    if "voice_bridge_discord" in patch:
        out["voice_bridge_discord"] = bool(patch["voice_bridge_discord"])
    if "voice_realtime_enabled" in patch:
        out["voice_realtime_enabled"] = bool(patch["voice_realtime_enabled"])
    if "voice_discord_vc_enabled" in patch:
        out["voice_discord_vc_enabled"] = bool(patch["voice_discord_vc_enabled"])

    _require_deps().apply_voice_operator_row(out)
    _require_deps().invalidate_operator_settings()
    if any(
        k in patch
        for k in (
            "voice_api_base_url",
            "voice_api_key",
            "voice_stt_model",
            "voice_tts_model",
            "voice_tts_voice",
        )
    ):
        _require_deps().sync_single_provider_endpoint(
            "voice_stt",
            label="Voice STT provider",
            base_url=out.get("voice_api_base_url"),
            api_key=out.get("voice_api_key"),
            api_header_name="Authorization",
            model_default=out.get("voice_stt_model") or "whisper-1",
        )
        _require_deps().sync_single_provider_endpoint(
            "voice_tts",
            label="Voice TTS provider",
            base_url=out.get("voice_api_base_url"),
            api_key=out.get("voice_api_key"),
            api_header_name="Authorization",
            model_default=out.get("voice_tts_model") or "tts-1",
            options_json={"voice": out.get("voice_tts_voice") or "alloy"},
        )
    _require_deps().invalidate_voice_provider_specs_cache()
