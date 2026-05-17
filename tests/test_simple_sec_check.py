"""Tests for SimpleSecCheck integration tools."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from plugins.tools.integrations.simple_sec_check import simple_sec_check as ssc


def test_parse_token_plain_and_json():
    assert ssc._parse_token("ssc_abc") == "ssc_abc"
    assert ssc._parse_token('{"token":"ssc_x"}') == "ssc_x"


@patch.dict("os.environ", {"SSC_API_KEY": "ssc_test", "SSC_BASE_URL": "https://scan.example.com"}, clear=False)
def test_security_scan_list_ok():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.content = b'[{"id":"1","status":"done"}]'
    mock_resp.json.return_value = [{"id": "1", "status": "done"}]
    with patch("httpx.Client") as client_cls:
        client_cls.return_value.__enter__.return_value.request.return_value = mock_resp
        out = json.loads(ssc.security_scan_list({"limit": 5}))
    assert out["ok"] is True
    assert out["count"] == 1


@patch.dict("os.environ", {}, clear=True)
def test_security_scan_list_no_key():
    with patch.object(ssc.db, "user_secret_get_plaintext", return_value=None):
        out = json.loads(ssc.security_scan_list({}))
    assert out["ok"] is False
    assert "SSC_API_KEY" in out["error"]


@patch.dict("os.environ", {"SSC_API_KEY": "ssc_test"}, clear=False)
def test_security_scan_start_sends_repo_url():
    mock_resp = MagicMock()
    mock_resp.status_code = 201
    mock_resp.content = b'{"id":"scan-99","status":"queued"}'
    mock_resp.json.return_value = {"id": "scan-99", "status": "queued"}
    with patch("httpx.Client") as client_cls:
        client = client_cls.return_value.__enter__.return_value
        client.request.return_value = mock_resp
        out = json.loads(
            ssc.security_scan_start(
                {"repo_url": "https://github.com/org/repo.git", "branch": "main"},
                None,
            )
        )
    assert out["ok"] is True
    assert out["scan_id"] == "scan-99"
    call_kwargs = client.request.call_args.kwargs
    assert call_kwargs["json"]["repo_url"] == "https://github.com/org/repo.git"
    assert call_kwargs["json"]["branch"] == "main"


def test_schedule_allowlist_includes_scan_tools():
    from apps.backend.infrastructure.coding_schedule_execution import _schedule_tool_allowlist

    names = _schedule_tool_allowlist(
        {"security_scan": True},
        "Security remediation",
        "security_scan_start",
    )
    assert "security_scan_start" in names
    assert "coding_write_file" in names
