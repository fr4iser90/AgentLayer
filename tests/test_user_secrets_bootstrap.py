"""User secrets bootstrap snippets and status tool."""

from __future__ import annotations

import json
import uuid
from unittest.mock import patch

from apps.backend.infrastructure.user_secrets_bootstrap import (
    build_user_secrets_bootstrap_snippet,
    build_workspace_bound_snippet,
)
from plugins.tools.platform.secrets.user_secrets_status import (
    user_secrets_status,
)


def test_bootstrap_lists_configured_keys_without_values() -> None:
    uid = uuid.uuid4()
    with patch(
        "apps.backend.infrastructure.user_secrets_bootstrap.config"
    ) as cfg:
        cfg.SECRETS_MASTER_KEY = "test-key"
        with patch(
            "apps.backend.infrastructure.db.db.user_secret_list_service_keys",
            return_value=["github_pat", "ssc_api_key"],
        ):
            snip = build_user_secrets_bootstrap_snippet(uid)
    assert "ssc_api_key" in snip
    assert "github_pat" in snip
    assert "do **not** ask" in snip.lower() or "Do **not** ask" in snip
    assert "ssc_" not in snip or "paste" in snip.lower()


def test_workspace_bound_snippet() -> None:
    snip = build_workspace_bound_snippet(
        {
            "id": "wid-1",
            "name": "AgentLayer",
            "git_url": "https://github.com/fr4iser90/AgentLayer",
            "path": "/code",
        }
    )
    assert "AgentLayer" in snip
    assert "security_auditor" in snip


def test_user_secrets_status_tool() -> None:
    uid = uuid.uuid4()
    with patch(
        "plugins.tools.platform.secrets.user_secrets_status.config"
    ) as cfg:
        cfg.SECRETS_MASTER_KEY = "k"
        with patch(
            "plugins.tools.platform.secrets.user_secrets_status.get_identity",
            return_value=(1, uid),
        ):
            with patch(
                "plugins.tools.platform.secrets.user_secrets_status.db.user_secret_list_service_keys",
                return_value=["ssc_api_key"],
            ):
                with patch(
                    "plugins.tools.platform.secrets.user_secrets_status._catalog_keys",
                    return_value=["ssc_api_key", "github_pat"],
                ):
                    out = json.loads(user_secrets_status({}))
    assert out["ok"] is True
    assert "ssc_api_key" in out["configured"]
