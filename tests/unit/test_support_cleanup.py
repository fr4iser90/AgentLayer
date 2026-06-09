"""Unit tests for E2E resource title matchers (no live server)."""

from __future__ import annotations

from tests.e2e.support.cleanup import (
    E2E_IDOR_PREFIX,
    _is_e2e_idor_conversation_title,
    _is_e2e_idor_dashboard_title,
    _is_e2e_idor_workspace_name,
)


def test_conversation_title_matches_new_and_legacy() -> None:
    assert _is_e2e_idor_conversation_title(f"{E2E_IDOR_PREFIX} conversation auth probe abc")
    assert _is_e2e_idor_conversation_title("IDOR conv 353b8977")
    assert not _is_e2e_idor_conversation_title("My real chat")
    assert not _is_e2e_idor_conversation_title("IDOR conv nothex")


def test_dashboard_title_matches_new_and_legacy() -> None:
    assert _is_e2e_idor_dashboard_title(f"{E2E_IDOR_PREFIX} dashboard read probe abc")
    assert _is_e2e_idor_dashboard_title("IDOR probe deadbeef")
    assert _is_e2e_idor_dashboard_title("IDOR editor patch abcdef01-edited")
    assert _is_e2e_idor_dashboard_title("IDOR public public-deadbeef")
    assert not _is_e2e_idor_dashboard_title("Project dashboard")


def test_workspace_name_matches_e2e_prefix() -> None:
    assert _is_e2e_idor_workspace_name("e2e-idor-ws-deadbeef01")
    assert not _is_e2e_idor_workspace_name("my-project")
