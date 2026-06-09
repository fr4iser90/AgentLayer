"""Unit tests: user secrets isolated per user (DB + LLM bootstrap + tools)."""

from __future__ import annotations

import json
import uuid
from unittest.mock import patch

from apps.backend.infrastructure.user_secrets_bootstrap import build_user_secrets_bootstrap_snippet
from plugins.tools.platform.secrets.user_secrets_status import user_secrets_status


def test_bootstrap_snippet_per_user_lists_only_that_users_keys() -> None:
    user_a = uuid.uuid4()
    user_b = uuid.uuid4()

    def _keys(uid: uuid.UUID) -> list[str]:
        if uid == user_a:
            return ["e2e.idor.admin_only"]
        if uid == user_b:
            return ["e2e.idor.b_only"]
        return []

    with patch(
        "apps.backend.infrastructure.user_secrets_bootstrap.config"
    ) as cfg:
        cfg.SECRETS_MASTER_KEY = "test-key"
        with patch(
            "apps.backend.infrastructure.db.db.user_secret_list_service_keys",
            side_effect=_keys,
        ):
            snip_a = build_user_secrets_bootstrap_snippet(user_a)
            snip_b = build_user_secrets_bootstrap_snippet(user_b)

    assert "e2e.idor.admin_only" in snip_a
    assert "e2e.idor.admin_only" not in snip_b
    assert "e2e.idor.b_only" in snip_b
    assert "e2e.idor.b_only" not in snip_a
    assert "values are never shown" in snip_a.lower() or "never shown" in snip_a.lower()


def test_user_secrets_status_never_includes_plaintext_values() -> None:
    uid = uuid.uuid4()
    with patch("plugins.tools.platform.secrets.user_secrets_status.config") as cfg:
        cfg.SECRETS_MASTER_KEY = "k"
        with patch(
            "plugins.tools.platform.secrets.user_secrets_status.get_identity",
            return_value=(1, uid),
        ):
            with patch(
                "plugins.tools.platform.secrets.user_secrets_status.db.user_secret_list_service_keys",
                return_value=["gmail"],
            ):
                with patch(
                    "plugins.tools.platform.secrets.user_secrets_status._catalog_keys",
                    return_value=["gmail"],
                ):
                    out = json.loads(user_secrets_status({}))

    raw = json.dumps(out)
    assert "app_password" not in raw
    assert "sk-" not in raw
    assert out["configured"] == ["gmail"]
    assert "configured" in out
    assert "secret" not in raw.lower() or "user_secrets_status" in raw
