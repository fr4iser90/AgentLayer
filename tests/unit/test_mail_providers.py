"""Mail provider resolution (phase 2)."""

from __future__ import annotations

from unittest.mock import patch

from plugins.tools.integrations.mail.lib.providers import MAIL_PROVIDERS, provider_ids
from plugins.tools.integrations.mail.lib.resolve import resolve_mail_session


def test_mail_provider_ids() -> None:
    assert "gmail" in provider_ids()
    assert "outlook" in provider_ids()
    assert "gmx" in provider_ids()


def test_resolve_mail_session_no_user() -> None:
    out = resolve_mail_session({})
    assert isinstance(out, str)
    assert "identity" in out.lower()


def test_resolve_mail_session_gmail_secret() -> None:
    with patch("plugins.tools.integrations.mail.lib.resolve.get_identity", return_value=(1, 42)):
        with patch(
            "plugins.tools.integrations.mail.lib.resolve.db.user_secret_get_plaintext",
            return_value='{"email":"u@gmail.com","app_password":"abcd efgh ijkl mnop"}',
        ):
            session = resolve_mail_session({"provider": "gmail"})
    assert not isinstance(session, str)
    assert session.provider.id == "gmail"
    assert session.email == "u@gmail.com"
    assert session.password == "abcdefghijklmnop"


def test_resolve_mail_session_unified_mail_json() -> None:
    with patch("plugins.tools.integrations.mail.lib.resolve.get_identity", return_value=(1, 42)):
        with patch(
            "plugins.tools.integrations.mail.lib.resolve.db.user_secret_get_plaintext",
            side_effect=lambda _uid, key: (
                '{"provider":"outlook","email":"u@outlook.com","password":"secret"}'
                if key == "mail"
                else None
            ),
        ):
            session = resolve_mail_session({})
    assert not isinstance(session, str)
    assert session.provider.id == "outlook"


def test_mail_providers_have_imap_hosts() -> None:
    for pid, spec in MAIL_PROVIDERS.items():
        assert spec.imap_host
        assert spec.secret_keys
