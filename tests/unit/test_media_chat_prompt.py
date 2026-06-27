"""Tests for media library chat system prompt snippet."""

from __future__ import annotations

import uuid
from unittest.mock import patch

from apps.backend.domain.agent_runtime.media_prompt import build_media_library_context_snippet


def test_admin_snippet_when_library_disabled() -> None:
    uid = uuid.uuid4()
    with patch("apps.backend.domain.agent_runtime.media_prompt.media_db.media_tables_exist", return_value=True):
        with patch(
            "apps.backend.domain.agent_runtime.media_prompt.media_policy.effective_media_library_enabled",
            return_value=False,
        ):
            snip = build_media_library_context_snippet(
                user_id=uid,
                tenant_id=1,
                caller_is_admin=True,
            )
    assert "delegate" in snip and "operator" in snip
    assert "settings_get" in snip
    assert "settings_patch" in snip
    assert "media_library_enabled" not in snip
    assert "coding" in snip.lower()


def test_non_admin_snippet_when_library_disabled() -> None:
    uid = uuid.uuid4()
    with patch("apps.backend.domain.agent_runtime.media_prompt.media_db.media_tables_exist", return_value=True):
        with patch(
            "apps.backend.domain.agent_runtime.media_prompt.media_policy.effective_media_library_enabled",
            return_value=False,
        ):
            snip = build_media_library_context_snippet(
                user_id=uid,
                tenant_id=1,
                caller_is_admin=False,
            )
    assert "delegate" not in snip.lower()
    assert "admin" in snip.lower()
