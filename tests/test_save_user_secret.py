"""Tests for save_user_secret tool and service_key validation."""

from __future__ import annotations

import json
import uuid
from unittest.mock import patch

from apps.backend.infrastructure.secret_otp_bundle import validate_user_secret_service_key
from plugins.tools.capabilities.platform.secrets.save_user_secret import save_user_secret


def test_validate_user_secret_service_key_format():
    assert validate_user_secret_service_key("my_integration") == "my_integration"
    assert validate_user_secret_service_key("Invalid Key!") is None
    assert validate_user_secret_service_key("") is None


@patch("plugins.tools.capabilities.platform.secrets.save_user_secret.config")
def test_save_user_secret_requires_master_key(mock_cfg):
    mock_cfg.SECRETS_MASTER_KEY = None
    out = json.loads(save_user_secret({"service_key": "my_integration", "secret": "x"}))
    assert out["ok"] is False


@patch("plugins.tools.capabilities.platform.secrets.save_user_secret.config")
@patch("plugins.tools.capabilities.platform.secrets.save_user_secret.get_identity")
def test_save_user_secret_requires_identity(mock_ident, mock_cfg):
    mock_cfg.SECRETS_MASTER_KEY = "test-key"
    mock_ident.return_value = (1, None)
    out = json.loads(save_user_secret({"service_key": "my_integration", "secret": "x"}))
    assert out["ok"] is False


@patch("plugins.tools.capabilities.platform.secrets.save_user_secret.config")
@patch("plugins.tools.capabilities.platform.secrets.save_user_secret.get_identity")
def test_save_user_secret_rejects_invalid_service_key(mock_ident, mock_cfg):
    mock_cfg.SECRETS_MASTER_KEY = "test-key"
    mock_ident.return_value = (1, uuid.uuid4())
    out = json.loads(
        save_user_secret({"service_key": "not valid!", "secret": "x"})
    )
    assert out["ok"] is False
    assert "catalog_service_keys" in out


@patch("plugins.tools.capabilities.platform.secrets.save_user_secret.db")
@patch("plugins.tools.capabilities.platform.secrets.save_user_secret.config")
@patch("plugins.tools.capabilities.platform.secrets.save_user_secret.get_identity")
def test_save_user_secret_upserts(mock_ident, mock_cfg, mock_db):
    mock_cfg.SECRETS_MASTER_KEY = "test-key"
    uid = uuid.uuid4()
    mock_ident.return_value = (1, uid)
    sk = "custom_integration_key"
    token = "secret-value"
    out = json.loads(
        save_user_secret(
            {"service_key": sk, "secret": token},
        )
    )
    assert out["ok"] is True
    assert out["stored"] is True
    assert out["service_key"] == sk
    mock_db.user_secret_upsert.assert_called_once_with(uid, sk, token)


@patch("plugins.tools.capabilities.platform.secrets.save_user_secret.db")
@patch("plugins.tools.capabilities.platform.secrets.save_user_secret.config")
@patch("plugins.tools.capabilities.platform.secrets.save_user_secret.get_identity")
def test_save_user_secret_json_object_secret(mock_ident, mock_cfg, mock_db):
    mock_cfg.SECRETS_MASTER_KEY = "test-key"
    uid = uuid.uuid4()
    mock_ident.return_value = (1, uid)
    out = json.loads(
        save_user_secret(
            {
                "service_key": "gmail",
                "secret": {"email": "a@b.com", "app_password": "pw"},
            },
        )
    )
    assert out["ok"] is True
    assert out["service_key"] == "gmail"
    mock_db.user_secret_upsert.assert_called_once()
    _uid, sk, plaintext = mock_db.user_secret_upsert.call_args[0]
    assert sk == "gmail"
    assert "app_password" in plaintext
