"""Tests for request_user_secret tool and secret_prompt WebSocket payload."""

from __future__ import annotations

import json
import uuid
from unittest.mock import patch

import pytest

from plugins.tools.capabilities.platform.secrets.request_user_secret import (
    request_user_secret,
)


@patch("plugins.tools.capabilities.platform.secrets.request_user_secret.config")
def test_request_user_secret_requires_master_key(mock_cfg):
    mock_cfg.SECRETS_MASTER_KEY = ""
    out = json.loads(request_user_secret({"service_key": "ssc_api_key"}))
    assert out["ok"] is False


@patch("plugins.tools.capabilities.platform.secrets.request_user_secret.config")
@patch("plugins.tools.capabilities.platform.secrets.request_user_secret.get_identity")
def test_request_user_secret_requires_identity(mock_ident, mock_cfg):
    mock_cfg.SECRETS_MASTER_KEY = "x" * 32
    mock_ident.return_value = (None, None)
    out = json.loads(request_user_secret({"service_key": "ssc_api_key"}))
    assert out["ok"] is False


@patch("plugins.tools.capabilities.platform.secrets.request_user_secret.form_spec_for_service_key")
@patch("plugins.tools.capabilities.platform.secrets.request_user_secret._catalog_service_keys")
@patch("plugins.tools.capabilities.platform.secrets.request_user_secret.config")
@patch("plugins.tools.capabilities.platform.secrets.request_user_secret.get_identity")
def test_request_user_secret_emits_payload(
    mock_ident, mock_cfg, mock_catalog, mock_form
):
    mock_cfg.SECRETS_MASTER_KEY = "x" * 32
    mock_ident.return_value = (uuid.uuid4(), uuid.uuid4())
    mock_catalog.return_value = ["ssc_api_key"]
    mock_form.return_value = {
        "title": "SSC key",
        "fields": [{"name": "token", "type": "password", "required": True}],
    }
    out = json.loads(
        request_user_secret(
            {"service_key": "ssc_api_key", "reason": "expired"}
        )
    )
    assert out["ok"] is True
    assert out["ui_emitted"] is True
    sp = out["secret_prompt"]
    assert sp["service_key"] == "ssc_api_key"
    assert sp["mode"] == "authenticated"
    assert sp["reason"] == "expired"
    assert sp["fields"][0]["name"] == "token"


def test_emit_secret_prompt_from_tool_result():
    import asyncio

    from apps.backend.domain.agent import _emit_secret_prompt_from_tool_result

    emitted: list[dict] = []

    async def capture(ev: dict):
        emitted.append(ev)

    payload = json.dumps(
        {
            "ok": True,
            "secret_prompt": {
                "prompt_id": "p1",
                "service_key": "ssc_api_key",
                "mode": "authenticated",
                "title": "T",
                "fields": [],
            },
        }
    )

    async def run():
        await _emit_secret_prompt_from_tool_result(
            "request_user_secret",
            payload,
            event_emit=capture,
            agent_run_id="run-1",
        )
        await _emit_secret_prompt_from_tool_result(
            "save_user_secret",
            payload,
            event_emit=capture,
            agent_run_id="run-1",
        )

    asyncio.run(run())
    assert len(emitted) == 1
    assert emitted[0]["type"] == "agent.secret_prompt"
    assert emitted[0]["prompt_id"] == "p1"
    assert emitted[0]["service_key"] == "ssc_api_key"
