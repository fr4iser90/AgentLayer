"""Effective voice feature flags (operator_settings + user_voice_prefs + env)."""

from __future__ import annotations

import uuid
from typing import Any, Protocol

_DEFAULT_OPERATOR: dict[str, Any] = {
    "voice_enabled": False,
    "voice_provider_id": None,
    "voice_stt_provider_id": None,
    "voice_tts_provider_id": None,
    "voice_api_base_url": None,
    "voice_api_key": None,
    "voice_stt_model": "whisper-1",
    "voice_tts_model": "tts-1",
    "voice_tts_voice": "alloy",
    "voice_max_seconds": 120,
    "voice_max_bytes": 10_485_760,
    "voice_bridge_telegram": True,
    "voice_bridge_discord": True,
    "voice_realtime_enabled": False,
    "voice_discord_vc_enabled": False,
}

_DEFAULT_USER: dict[str, Any] = {
    "input_enabled": True,
    "output_enabled": False,
    "language": "de",
    "voice_id": None,
    "mode_web": "push_to_talk",
    "mode_telegram": "text_only",
    "mode_discord": "text_only",
    "edit_transcript_before_send": True,
}


class VoicePolicyDependencies(Protocol):
    def operator_voice_row(self) -> dict[str, Any] | None: ...

    def user_voice_prefs_get(self, user_id: uuid.UUID) -> dict[str, Any] | None: ...

    def user_voice_prefs_upsert(
        self, tenant_id: int, user_id: uuid.UUID, values: dict[str, Any]
    ) -> None: ...

    def active_voice_stt_spec(self) -> Any | None: ...

    def active_voice_tts_spec(self) -> Any | None: ...

    def voice_auth_headers(self, spec: Any) -> dict[str, str]: ...


_deps: VoicePolicyDependencies | None = None


def register_voice_policy_dependencies(deps: VoicePolicyDependencies) -> None:
    global _deps
    _deps = deps


def operator_voice_row() -> dict[str, Any]:
    out = dict(_DEFAULT_OPERATOR)
    if _deps is None:
        return out
    try:
        row = _deps.operator_voice_row()
    except Exception:
        return out
    if not isinstance(row, dict):
        return out
    out.update({k: v for k, v in row.items() if k in _DEFAULT_OPERATOR and v is not None})
    return out


def user_voice_prefs_get(user_id: uuid.UUID) -> dict[str, Any]:
    out = dict(_DEFAULT_USER)
    if _deps is None:
        return out
    try:
        row = _deps.user_voice_prefs_get(user_id)
    except Exception:
        return out
    if not isinstance(row, dict):
        return out
    out.update({k: v for k, v in row.items() if k in _DEFAULT_USER and v is not None})
    return out


def user_voice_prefs_upsert(tenant_id: int, user_id: uuid.UUID, patch: dict[str, Any]) -> None:
    cur = user_voice_prefs_get(user_id)
    cur.update({k: v for k, v in patch.items() if k in _DEFAULT_USER})
    if _deps is not None:
        _deps.user_voice_prefs_upsert(tenant_id, user_id, cur)


def effective_voice_enabled(*, user_id: uuid.UUID | None = None) -> bool:
    if not bool(operator_voice_row().get("voice_enabled")):
        return False
    if user_id is None:
        return True
    prefs = user_voice_prefs_get(user_id)
    return bool(prefs.get("input_enabled", True)) or bool(prefs.get("output_enabled", False))


def effective_voice_input(*, user_id: uuid.UUID, channel: str) -> bool:
    if not effective_voice_enabled(user_id=user_id):
        return False
    op = operator_voice_row()
    if channel == "telegram" and not bool(op.get("voice_bridge_telegram", True)):
        return False
    if channel == "discord" and not bool(op.get("voice_bridge_discord", True)):
        return False
    prefs = user_voice_prefs_get(user_id)
    if not bool(prefs.get("input_enabled", True)):
        return False
    mode_web = str(prefs.get("mode_web") or "off")
    if channel == "web" and mode_web == "off":
        return False
    return True


def effective_voice_realtime(*, user_id: uuid.UUID) -> bool:
    if not effective_voice_enabled(user_id=user_id):
        return False
    if not bool(operator_voice_row().get("voice_realtime_enabled")):
        return False
    prefs = user_voice_prefs_get(user_id)
    if not bool(prefs.get("input_enabled", True)):
        return False
    mode = str(prefs.get("mode_web") or "push_to_talk")
    return mode in ("realtime", "hands_free")


def effective_discord_vc(*, user_id: uuid.UUID | None = None) -> bool:
    if not effective_voice_enabled(user_id=user_id):
        return False
    return bool(operator_voice_row().get("voice_discord_vc_enabled"))


def effective_voice_output(*, user_id: uuid.UUID, channel: str) -> bool:
    if not effective_voice_enabled(user_id=user_id):
        return False
    prefs = user_voice_prefs_get(user_id)
    if not bool(prefs.get("output_enabled", False)):
        return False
    # Web: output_enabled alone controls TTS; mode_web is for input (push-to-talk / hands-free).
    if channel == "web":
        return True
    mode_key = {"telegram": "mode_telegram", "discord": "mode_discord"}.get(channel)
    if not mode_key:
        return False
    mode = str(prefs.get(mode_key) or "text_only")
    return mode in ("voice_reply", "voice_both")


def effective_voice_limits() -> tuple[int, int]:
    op = operator_voice_row()
    try:
        max_sec = int(op.get("voice_max_seconds") or 120)
    except (TypeError, ValueError):
        max_sec = 120
    try:
        max_bytes = int(op.get("voice_max_bytes") or 10_485_760)
    except (TypeError, ValueError):
        max_bytes = 10_485_760
    return max(5, min(max_sec, 600)), max(64_000, min(max_bytes, 52_428_800))


def voice_api_credentials() -> tuple[str, str]:
    spec = _deps.active_voice_stt_spec() if _deps is not None else None
    if spec and spec.base_url:
        return spec.base_url.rstrip("/"), (spec.api_key or "").strip()
    return "", ""


def active_voice_stt_spec() -> Any | None:
    return _deps.active_voice_stt_spec() if _deps is not None else None


def active_voice_tts_spec() -> Any | None:
    return _deps.active_voice_tts_spec() if _deps is not None else None


def voice_auth_headers(spec: Any) -> dict[str, str]:
    if _deps is None:
        key = (getattr(spec, "api_key", "") or "").strip()
        if not key:
            return {}
        header = (getattr(spec, "api_header_name", "") or "Authorization").strip()
        if header.lower() == "authorization":
            return {"Authorization": f"Bearer {key}"}
        return {header: key}
    return _deps.voice_auth_headers(spec)


def voice_stt_model() -> str:
    spec = _deps.active_voice_stt_spec() if _deps is not None else None
    if spec and spec.model_stt:
        return spec.model_stt[:128]
    return ""


def voice_tts_model() -> str:
    spec = _deps.active_voice_tts_spec() if _deps is not None else None
    if spec and spec.model_tts:
        return spec.model_tts[:128]
    return ""


def effective_tts_voice(user_id: uuid.UUID) -> str:
    prefs = user_voice_prefs_get(user_id)
    custom = (str(prefs.get("voice_id") or "").strip())
    if custom:
        return custom[:64]
    spec = _deps.active_voice_tts_spec() if _deps is not None else None
    if spec and spec.model_tts_voice:
        return spec.model_tts_voice[:64]
    return "alloy"


def effective_stt_language(user_id: uuid.UUID) -> str | None:
    lang = (str(user_voice_prefs_get(user_id).get("language") or "").strip())
    return lang[:16] if lang else None
