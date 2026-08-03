from __future__ import annotations

from unittest.mock import patch

from apps.backend.infrastructure.legal import legal_content as lc


def test_substitute_entity_placeholders():
    text = "Name: {{legal_entity.name}}, Mail: {{legal_entity.email}}"
    out = lc._substitute_entity_placeholders(
        text,
        {"name": "ACME", "email": "a@b.de"},
    )
    assert out == "Name: ACME, Mail: a@b.de"


def test_legal_public_index_disabled_by_default():
    with patch.object(lc, "_cached_row", return_value={"legal_enabled": False, "legal_jurisdiction": "none"}):
        idx = lc.legal_public_index()
    assert idx["enabled"] is False
    assert idx["pages"] == []


def test_legal_page_body_from_de_file():
    row = {
        "legal_enabled": True,
        "legal_jurisdiction": "de",
        "legal_terms_enabled": False,
        "legal_entity_name": "Test GmbH",
        "legal_entity_address": "Berlin",
        "legal_entity_email": "legal@test.de",
        "legal_entity_phone": "",
        "legal_impressum_md": None,
        "legal_privacy_md": None,
        "legal_terms_md": None,
    }
    with patch.object(lc, "_cached_row", return_value=row):
        body = lc.legal_page_body_md("impressum")
    assert body is not None
    assert "Test GmbH" in body
    assert "legal@test.de" in body


def test_legal_override_wins_over_file():
    row = {
        "legal_enabled": True,
        "legal_jurisdiction": "de",
        "legal_terms_enabled": False,
        "legal_entity_name": "X",
        "legal_entity_address": "",
        "legal_entity_email": "",
        "legal_entity_phone": "",
        "legal_impressum_md": "# Custom impressum",
        "legal_privacy_md": None,
        "legal_terms_md": None,
    }
    with patch.object(lc, "_cached_row", return_value=row):
        body = lc.legal_page_body_md("impressum")
    assert body == "# Custom impressum"
