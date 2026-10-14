"""DB overrides for external/Qwen runtime enabled flags."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

# Import order avoids circular init between operator_settings <-> readers.
import apps.backend.infrastructure.settings.operator_settings  # noqa: F401
import apps.backend.infrastructure.settings.operator_settings_readers as readers
from apps.backend.infrastructure.platform import config_external_runtimes as crt


def test_external_runtime_enabled_effective_env_default() -> None:
    with (
        patch.object(crt, "EXTERNAL_RUNTIME_ENABLED", True),
        patch.object(readers, "external_runtime_enabled_override", return_value=None),
    ):
        assert crt.external_runtime_enabled_effective() is True


def test_external_runtime_enabled_effective_db_override_wins() -> None:
    with (
        patch.object(crt, "EXTERNAL_RUNTIME_ENABLED", False),
        patch.object(readers, "external_runtime_enabled_override", return_value=True),
    ):
        assert crt.external_runtime_enabled_effective() is True


def test_qwen_runtime_enabled_effective_db_override_false() -> None:
    with (
        patch.object(crt, "QWEN_RUNTIME_ENABLED", True),
        patch.object(readers, "qwen_runtime_enabled_override", return_value=False),
    ):
        assert crt.qwen_runtime_enabled_effective() is False


def test_setup_catalog_includes_voice_and_runtimes() -> None:
    from apps.backend.domain.setup import catalog as mod

    merged = [{"id": "llama3", "owned_by": "provider_1"}]
    agentlayer = {
        "provider_1": {"reachable": True, "detail": None},
        "embedding": {"reachable": False, "configured": False},
    }
    spec = MagicMock(
        provider_id="provider_1",
        label="provider_1",
        source="db",
        base_url="http://host:11434",
        api_key=None,
    )
    with (
        patch.object(mod, "fetch_full_model_catalog", return_value=(merged, agentlayer)),
        patch.object(mod, "list_provider_specs", return_value=[spec]),
        patch.object(mod, "pick_reachable_catalog_provider", return_value="provider_1"),
        patch.object(
            mod,
            "enrich_setup_embedding_meta",
            side_effect=lambda emb, _providers: {
                **emb,
                "available_models": [],
                "chat_embed_opt_in": {"available": False},
            },
        ),
        patch.object(
            mod,
            "_setup_voice_summary",
            return_value={
                "stt_providers": [],
                "tts_providers": [],
                "voice_enabled": False,
                "voice_stt_provider_id": None,
                "voice_tts_provider_id": None,
                "voice_stt_model": None,
                "voice_tts_model": None,
            },
        ),
        patch.object(
            mod,
            "_setup_external_runtime_summary",
            return_value={
                "enabled": False,
                "env_enabled": False,
                "db_override": None,
                "qwen_enabled": True,
                "qwen_env_enabled": True,
                "qwen_db_override": None,
                "runtimes": [],
            },
        ),
    ):
        out = mod.build_setup_catalog()
    assert "voice" in out
    assert "external_runtimes" in out
    assert out["external_runtimes"]["qwen_enabled"] is True
