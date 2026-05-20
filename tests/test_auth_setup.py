"""Initial instance setup (POST /auth/setup, setup-status)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from apps.backend.domain import instance_setup as mod


def test_validate_setup_email_rejects_invalid() -> None:
    with pytest.raises(HTTPException) as exc:
        mod.validate_setup_email("not-an-email")
    assert exc.value.status_code == 400


def test_validate_setup_password_mismatch() -> None:
    with pytest.raises(HTTPException) as exc:
        mod.validate_setup_password("password1", "password2")
    assert exc.value.status_code == 400


def test_validate_setup_password_too_short() -> None:
    with pytest.raises(HTTPException) as exc:
        mod.validate_setup_password("short")
    assert exc.value.status_code == 400


def test_create_first_admin_when_already_configured() -> None:
    with patch.object(mod, "is_first_start", return_value=False):
        with pytest.raises(HTTPException) as exc:
            mod.create_first_admin(email="a@b.co", password="password1")
    assert exc.value.status_code == 409


def test_build_setup_status_needs_admin() -> None:
    with (
        patch.object(mod, "is_first_start", return_value=True),
        patch.object(mod, "catalog_llm_configured", return_value=False),
    ):
        st = mod.build_setup_status()
    assert st["needs_setup"] is True
    assert st["needs_admin"] is True
    assert st["needs_llm"] is False


def test_build_setup_status_needs_llm() -> None:
    with (
        patch.object(mod, "is_first_start", return_value=False),
        patch.object(mod, "catalog_llm_configured", return_value=False),
        patch.object(mod, "setup_preferences_saved", return_value=False),
    ):
        st = mod.build_setup_status()
    assert st["needs_setup"] is False
    assert st["needs_llm"] is True
    assert st["needs_provider_wizard"] is True


def test_build_setup_status_provider_wizard_done() -> None:
    with (
        patch.object(mod, "is_first_start", return_value=False),
        patch.object(mod, "catalog_llm_configured", return_value=True),
        patch.object(mod, "setup_preferences_saved", return_value=True),
    ):
        st = mod.build_setup_status()
    assert st["needs_provider_wizard"] is False


def test_setup_admin_claim_does_not_exit() -> None:
    with (
        patch.object(mod, "is_first_start", return_value=True),
        patch.object(mod, "try_create_initial_admin_from_env", return_value=False),
    ):
        mod.setup_admin_claim_if_needed()


def test_emit_initial_setup_notice_delegates_to_banner() -> None:
    with patch.object(mod, "log_setup_token_banner_if_needed") as m:
        mod.emit_initial_setup_notice_at_end()
    m.assert_called_once()


def test_validate_setup_token_rejects_wrong() -> None:
    with (
        patch.object(mod, "is_first_start", return_value=True),
        patch.object(mod, "_setup_token_from_env", return_value="expected-secret"),
    ):
        with pytest.raises(HTTPException) as exc:
            mod.validate_setup_token("wrong")
    assert exc.value.status_code == 403


def test_validate_setup_token_accepts_env_token() -> None:
    with (
        patch.object(mod, "is_first_start", return_value=True),
        patch.object(mod, "_setup_token_from_env", return_value="expected-secret"),
    ):
        mod.validate_setup_token("expected-secret")


def test_build_setup_status_includes_token_meta() -> None:
    with (
        patch.object(mod, "is_first_start", return_value=True),
        patch.object(mod, "catalog_llm_configured", return_value=False),
        patch.object(mod, "_setup_token_from_env", return_value="x"),
    ):
        st = mod.build_setup_status()
    assert st["setup_token_required"] is True
    assert st["setup_token_source"] == "env"
