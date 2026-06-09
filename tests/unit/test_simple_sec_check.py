"""Tests for SimpleSecCheck integration tools."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from apps.backend.domain.security_scan import common as ssc_common
from plugins.tools.security.security_scan.agent_callback import (
    agent_callback,
)
from plugins.tools.security.security_scan.finding_policy_schema import (
    finding_policy_schema,
)
from plugins.tools.security.security_scan.findings import (
    findings,
)
from plugins.tools.security.security_scan.list import list
from plugins.tools.security.security_scan.resolve import (
    resolve,
)
from plugins.tools.security.security_scan.start import start
from plugins.tools.security.security_scan.status import (
    status,
)


def test_parse_token_plain_and_json():
    assert ssc_common.parse_token("ssc_abc") == "ssc_abc"
    assert ssc_common.parse_token('{"token":"ssc_x"}') == "ssc_x"


@patch.dict("os.environ", {"SSC_API_KEY": "ssc_test", "SSC_BASE_URL": "https://scan.example.com"}, clear=False)
def test_security_scan_list_ok():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.content = b'[{"id":"1","status":"done"}]'
    mock_resp.json.return_value = [{"id": "1", "status": "done"}]
    with patch("apps.backend.domain.security_scan.common.httpx.Client") as client_cls:
        client_cls.return_value.__enter__.return_value.request.return_value = mock_resp
        out = json.loads(list({"limit": 5}))
    assert out["ok"] is True
    assert out["count"] == 1


@patch.dict("os.environ", {}, clear=True)
def test_security_scan_list_no_key():
    with patch.object(ssc_common.db, "user_secret_get_plaintext", return_value=None):
        out = json.loads(list({}))
    assert out["ok"] is False
    assert "SSC_API_KEY" in out["error"]


@patch.dict("os.environ", {"SSC_API_KEY": "ssc_test"}, clear=False)
def test_security_scan_start_sends_repo_url():
    mock_resp = MagicMock()
    mock_resp.status_code = 201
    mock_resp.content = b'{"id":"scan-99","status":"queued"}'
    mock_resp.json.return_value = {"id": "scan-99", "status": "queued"}
    with patch("apps.backend.domain.security_scan.common.httpx.Client") as client_cls:
        client = client_cls.return_value.__enter__.return_value
        client.request.return_value = mock_resp
        out = json.loads(
            start(
                {"repo_url": "https://github.com/org/repo.git", "branch": "main"},
                None,
            )
        )
    assert out["ok"] is True
    assert out["scan_id"] == "scan-99"
    assert out["end_run_recommended"] is True
    call_kwargs = client.request.call_args.kwargs
    assert call_kwargs["json"]["repo_url"] == "https://github.com/org/repo.git"
    assert call_kwargs["json"]["branch"] == "main"


@patch.dict("os.environ", {"SSC_API_KEY": "ssc_test"}, clear=False)
def test_security_scan_resolve_started_defers():
    mock_resp = MagicMock()
    mock_resp.status_code = 202
    mock_resp.content = b'{"status":"started","scan_id":"abc"}'
    mock_resp.json.return_value = {
        "status": "started",
        "scan_id": "abc",
        "status_poll_path": "/api/v1/scans/abc/status",
    }
    with patch("apps.backend.domain.security_scan.common.httpx.Client") as client_cls:
        client = client_cls.return_value.__enter__.return_value
        client.request.return_value = mock_resp
        out = json.loads(
            resolve(
                {"repo_url": "https://github.com/org/repo.git", "findings_severity": "CRITICAL,HIGH"},
                None,
            )
        )
    assert out["ok"] is True
    assert out["defer"] is True
    assert out["end_run_recommended"] is True
    assert out["scan_id"] == "abc"
    assert "resolve-scan" in client.request.call_args[0][1]
    body = client.request.call_args.kwargs["json"]
    assert body["findings_severity"] == "CRITICAL,HIGH"
    assert body["findings_limit"] == 50


@patch.dict("os.environ", {"SSC_API_KEY": "ssc_test"}, clear=False)
def test_security_scan_resolve_ready_includes_findings():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "status": "ready",
        "scan_id": "done-1",
        "findings": [{"severity": "HIGH", "path": "a.py", "rule_id": "r1", "message": "x"}],
        "summary": {"total_vulnerabilities": 1},
    }
    mock_resp.content = b"{}"
    with patch("apps.backend.domain.security_scan.common.httpx.Client") as client_cls:
        client_cls.return_value.__enter__.return_value.request.return_value = mock_resp
        out = json.loads(
            resolve({"repo_url": "https://github.com/org/repo.git"}, None)
        )
    assert out["status"] == "ready"
    assert out["defer"] is False
    assert len(out["findings"]) == 1
    assert out["findings"][0]["severity"] == "HIGH"
    guidance = " ".join(out["agent_guidance"])
    assert "finding_policy_schema" in guidance
    assert "finding-policy.json" in guidance
    assert "nosec" in guidance.lower()


@patch.dict("os.environ", {"SSC_API_KEY": "ssc_test"}, clear=False)
def test_security_scan_resolve_merges_api_agent_guidance():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "status": "ready",
        "scan_id": "done-2",
        "agent_guidance": ["SSC custom FP workflow note."],
        "findings": [{"severity": "HIGH", "path": "a.py", "rule_id": "r1"}],
    }
    mock_resp.content = b"{}"
    with patch("apps.backend.domain.security_scan.common.httpx.Client") as client_cls:
        client_cls.return_value.__enter__.return_value.request.return_value = mock_resp
        out = json.loads(
            resolve({"repo_url": "https://github.com/org/repo.git"}, None)
        )
    guidance = out["agent_guidance"]
    assert "SSC custom FP workflow note." in guidance
    assert any("finding_policy_schema" in g for g in guidance)


@patch.dict("os.environ", {"SSC_API_KEY": "ssc_test"}, clear=False)
def test_security_scan_status_uses_status_endpoint():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"scan_id": "x", "status": "running", "progress": 42.5}
    mock_resp.content = b"{}"
    with patch("apps.backend.domain.security_scan.common.httpx.Client") as client_cls:
        client = client_cls.return_value.__enter__.return_value
        client.request.return_value = mock_resp
        out = json.loads(status({"scan_id": "x"}))
    assert out["still_running"] is True
    assert out["end_run_recommended"] is True
    assert "/status" in client.request.call_args[0][1]


@patch.dict("os.environ", {"SSC_API_KEY": "ssc_test"}, clear=False)
def test_security_scan_findings_pagination_params():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "findings": [],
        "pagination": {"has_more": True, "next_path": "/api/v1/scans/s1/findings?limit=50&offset=50"},
        "summary": {"total_vulnerabilities": 87},
    }
    mock_resp.content = b"{}"
    with patch("apps.backend.domain.security_scan.common.httpx.Client") as client_cls:
        client = client_cls.return_value.__enter__.return_value
        client.request.return_value = mock_resp
        out = json.loads(
            findings(
                {"scan_id": "s1", "limit": 50, "offset": 0, "severity": "CRITICAL,HIGH"}
            )
        )
    assert out["pagination"]["has_more"] is True
    params = client.request.call_args.kwargs["params"]
    assert params["limit"] == 50
    assert params["offset"] == 0
    assert params["severity"] == "CRITICAL,HIGH"


@patch.dict("os.environ", {"SSC_API_KEY": "ssc_test"}, clear=False)
def test_security_scan_findings_409_retry_hint():
    mock_resp = MagicMock()
    mock_resp.status_code = 409
    mock_resp.json.return_value = {"detail": "scan still running"}
    mock_resp.content = b"{}"
    mock_resp.reason_phrase = "Conflict"
    with patch("apps.backend.domain.security_scan.common.httpx.Client") as client_cls:
        client_cls.return_value.__enter__.return_value.request.return_value = mock_resp
        out = json.loads(findings({"scan_id": "s1"}))
    assert out["ok"] is False
    assert out["retry_later"] is True
    assert out["agent_guidance"]


@patch.dict("os.environ", {"SSC_API_KEY": "ssc_test"}, clear=False)
def test_security_scan_agent_callback():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"accepted": True, "scan_id": "new-scan"}
    mock_resp.content = b"{}"
    with patch("apps.backend.domain.security_scan.common.httpx.Client") as client_cls:
        client = client_cls.return_value.__enter__.return_value
        client.request.return_value = mock_resp
        out = json.loads(
            agent_callback(
                {"target_id": "tgt-1", "branch_name": "fix/ssc-1", "trigger_rescan": True}
            )
        )
    assert out["ok"] is True
    assert out["scan_id"] == "new-scan"
    assert out["end_run_recommended"] is True
    assert "agent-callback" in client.request.call_args[0][1]


@patch.dict("os.environ", {"SSC_API_KEY": "ssc_test"}, clear=False)
def test_security_scan_findings_poll_path():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"findings": [{"severity": "LOW", "path": "b.py"}]}
    mock_resp.content = b"{}"
    with patch("apps.backend.domain.security_scan.common.httpx.Client") as client_cls:
        client = client_cls.return_value.__enter__.return_value
        client.request.return_value = mock_resp
        out = json.loads(
            findings(
                {"poll_path": "/api/v1/scans/s1/findings?limit=25&offset=25"}
            )
        )
    assert out["ok"] is True
    path = client.request.call_args[0][1]
    assert path.endswith("/findings")
    params = client.request.call_args.kwargs["params"]
    assert int(params["limit"]) == 25
    assert int(params["offset"]) == 25
    assert "finding_policy_schema" in " ".join(out["agent_guidance"])


@patch.dict("os.environ", {"SSC_API_KEY": "ssc_test"}, clear=False)
def test_security_scan_finding_policy_schema():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "semgrep": {"accepted_findings": [{"fields": ["rule_id", "path_regex"]}]},
        "notes": ["root dedupe ignored"],
        "agent_guidance": ["Call before editing .scanning/finding-policy.json"],
    }
    mock_resp.content = b"{}"
    with patch("apps.backend.domain.security_scan.common.httpx.Client") as client_cls:
        client = client_cls.return_value.__enter__.return_value
        client.request.return_value = mock_resp
        out = json.loads(
            finding_policy_schema({"tools": "semgrep,gitleaks"}, None)
        )
    assert out["ok"] is True
    assert "finding-policy/schema" in client.request.call_args[0][1]
    assert client.request.call_args.kwargs["params"]["tools"] == "semgrep,gitleaks"
    assert "semgrep" in out["schema"]
    assert out["notes"] == ["root dedupe ignored"]
    assert out["agent_guidance"] == ["Call before editing .scanning/finding-policy.json"]


@patch.dict("os.environ", {"SSC_API_KEY": "ssc_test"}, clear=False)
def test_security_scan_finding_policy_schema_nested_schema_key():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "schema": {"bandit": {"accepted_findings": []}},
        "notes": "ok",
    }
    mock_resp.content = b"{}"
    with patch("apps.backend.domain.security_scan.common.httpx.Client") as client_cls:
        client_cls.return_value.__enter__.return_value.request.return_value = mock_resp
        out = json.loads(finding_policy_schema({}, None))
    assert out["schema"] == {"bandit": {"accepted_findings": []}}


def test_schedule_allowlist_includes_scan_tools():
    from apps.backend.infrastructure.coding_schedule_execution import _schedule_tool_allowlist

    names = _schedule_tool_allowlist(
        {"security_scan": True},
        "Security remediation",
        "resolve",
    )
    assert "finding_policy_schema" in names
    assert "resolve" in names
    assert "status" in names
    assert "write_file" in names
