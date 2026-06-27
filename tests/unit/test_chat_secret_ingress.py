"""Tests for chat secret ingress (ADR 0006 MVP)."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest
from cryptography.fernet import Fernet


def test_rewrite_heuristic_disabled_no_change(monkeypatch: pytest.MonkeyPatch) -> None:
    import apps.backend.infrastructure.platform.config as cmod
    from apps.backend.infrastructure.platform.chat_secret_ingress import rewrite_user_text

    monkeypatch.setattr(cmod, "CHAT_SECRET_HEURISTIC_REDACT_ENABLED", False)
    uid = uuid.uuid4()
    raw = "key sk-1234567890abcdefghijklmnop"
    s, h, v = rewrite_user_text(raw, tenant_id=1, user_id=uid)
    assert h == 0
    assert v == 0
    assert s == raw


def test_rewrite_heuristic_redacts_openai_sk(monkeypatch: pytest.MonkeyPatch) -> None:
    import apps.backend.infrastructure.platform.config as cmod
    from apps.backend.infrastructure.platform import chat_secret_ingress as csi

    monkeypatch.setattr(cmod, "CHAT_SECRET_HEURISTIC_REDACT_ENABLED", True)
    uid = uuid.uuid4()
    raw = "here sk-1234567890abcdefghijklmnop tail"
    s, h, v = csi.rewrite_user_text(raw, tenant_id=1, user_id=uid)
    assert v == 0
    assert h >= 1
    assert "sk-1234567890abcdefghijklmnop" not in s
    assert "[REDACTED:openai_sk]" in s


def test_resolve_roundtrip(monkeypatch: pytest.MonkeyPatch) -> None:
    import apps.backend.infrastructure.platform.config as cmod
    from apps.backend.infrastructure.platform import chat_secret_vault as vaultmod
    from apps.backend.infrastructure.platform import chat_secret_ingress as csi

    key = Fernet.generate_key().decode()
    monkeypatch.setattr(cmod, "CHAT_SECRET_INGRESS_ENABLED", True)
    monkeypatch.setattr(cmod, "CHAT_SECRET_VAULT_FERNET_KEY", key)

    uid = uuid.uuid4()
    vid = uuid.uuid4()

    def _get_plain(
        token_id: uuid.UUID,
        *,
        tenant_id: int,
        user_id: uuid.UUID,
        consume: bool = False,
    ) -> str | None:
        assert token_id == vid
        assert user_id == uid
        return "resolved-value"

    monkeypatch.setattr(vaultmod, "vault_get_plaintext", _get_plain)
    out = csi.resolve_placeholders_deep(
        {"discord_bot_token": f"[[agentlayer:secret:{vid}]]"},
        tenant_id=1,
        user_id=uid,
    )
    assert out["discord_bot_token"] == "resolved-value"


def test_json_redact_nested(monkeypatch: pytest.MonkeyPatch) -> None:
    import apps.backend.infrastructure.platform.config as cmod
    from apps.backend.infrastructure.platform import chat_secret_vault as vaultmod
    from apps.backend.infrastructure.platform import chat_secret_ingress as csi

    key = Fernet.generate_key().decode()
    monkeypatch.setattr(cmod, "CHAT_SECRET_INGRESS_ENABLED", True)
    monkeypatch.setattr(cmod, "CHAT_SECRET_VAULT_FERNET_KEY", key)
    vid = uuid.uuid4()
    monkeypatch.setattr(vaultmod, "vault_store", MagicMock(return_value=vid))
    uid = uuid.uuid4()
    s, h, v = csi.rewrite_user_text(
        '{"api_key": "longsecretvaluehere"}',
        tenant_id=1,
        user_id=uid,
    )
    assert v == 1
    assert h == 0
    assert "longsecretvaluehere" not in s
    assert f"[[agentlayer:secret:{vid}]]" in s


def test_vault_json_skipped_without_user_id(monkeypatch: pytest.MonkeyPatch) -> None:
    import apps.backend.infrastructure.platform.config as cmod
    from apps.backend.infrastructure.platform import chat_secret_vault as vaultmod
    from apps.backend.infrastructure.platform import chat_secret_ingress as csi

    key = Fernet.generate_key().decode()
    monkeypatch.setattr(cmod, "CHAT_SECRET_INGRESS_ENABLED", True)
    monkeypatch.setattr(cmod, "CHAT_SECRET_VAULT_FERNET_KEY", key)
    store = MagicMock(return_value=uuid.uuid4())
    monkeypatch.setattr(vaultmod, "vault_store", store)
    s, h, v = csi.rewrite_user_text(
        '{"api_key": "longsecretvaluehere"}',
        tenant_id=1,
        user_id=None,
    )
    assert v == 0
    assert store.call_count == 0
    assert "longsecretvaluehere" in s

