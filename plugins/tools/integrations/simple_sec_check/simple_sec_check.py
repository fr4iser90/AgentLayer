"""SimpleSecCheck (scan.fr4iser.com) API — security scans for Git repos.

Auth: env ``SSC_API_KEY`` + optional ``SSC_BASE_URL``, or per-user secret ``ssc_api_key``
(``ssc_…`` token, plain string or JSON ``{"token":"ssc_…"}``).
"""

from __future__ import annotations

import json
import os
import subprocess
from typing import Any, Callable
from urllib.parse import urljoin

import httpx

from apps.backend.domain.identity import get_identity
from apps.backend.infrastructure.db import db

__version__ = "1.0.0"
TOOL_ID = "simple_sec_check"
TOOL_BUCKET = "network"
TOOL_DOMAIN = "security_scan"
TOOL_LABEL = "SimpleSecCheck"
TOOL_DESCRIPTION = (
    "Start and read security scans on SimpleSecCheck (https://scan.fr4iser.com). "
    "Requires SSC_API_KEY / SSC_BASE_URL in docker/.env or user secret ssc_api_key."
)
TOOL_TRIGGERS = (
    "security scan",
    "simplesec",
    "ssc",
    "vulnerability scan",
    "semgrep",
    "sast",
)
TOOL_CAPABILITIES = ("security.scan",)
TOOL_SECRETS_REQUIRED = ("ssc_api_key",)
TOOL_USER_SECRET_FORMS: dict[str, dict[str, Any]] = {
    "ssc_api_key": {
        "title": "SimpleSecCheck API key",
        "help": (
            "Create under scan UI → API Keys (format ``ssc_…``). "
            "Paste the token alone or as JSON {\"token\":\"ssc_…\"}."
        ),
        "fields": [
            {
                "name": "token",
                "label": "API key (ssc_…)",
                "type": "password",
                "required": True,
            },
        ],
    }
}

USER_SECRET_KEY = "ssc_api_key"
DEFAULT_BASE_URL = "https://scan.fr4iser.com"
HTTP_TIMEOUT = 120.0
MAX_FINDINGS = 200


def _parse_token(raw: str) -> str:
    s = (raw or "").strip()
    if not s:
        return ""
    try:
        obj = json.loads(s)
    except json.JSONDecodeError:
        return s
    if isinstance(obj, dict):
        return str(obj.get("token") or obj.get("api_key") or "").strip()
    return s


def _api_key() -> str | None:
    _tid, uid = get_identity()
    if uid is not None:
        raw = db.user_secret_get_plaintext(uid, USER_SECRET_KEY)
        if raw:
            t = _parse_token(raw)
            if t:
                return t
    env_t = os.environ.get("SSC_API_KEY", "").strip()
    return env_t or None


def _base_url() -> str:
    env_b = os.environ.get("SSC_BASE_URL", "").strip().rstrip("/")
    if env_b:
        return env_b
    return DEFAULT_BASE_URL


def _auth_error() -> dict[str, Any]:
    return {
        "ok": False,
        "error": (
            "No SimpleSecCheck API key: set SSC_API_KEY in docker/.env (and optional SSC_BASE_URL), "
            f"or register user secret `{USER_SECRET_KEY}` via Settings → Connections / register_secrets "
            '(plain ssc_… or JSON {"token":"ssc_…"}).'
        ),
    }


def _headers(tok: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {tok}",
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "agentlayer-simple-sec-check-tool",
    }


def _request(
    method: str,
    path: str,
    *,
    params: dict[str, Any] | None = None,
    json_body: dict[str, Any] | None = None,
    timeout: float = HTTP_TIMEOUT,
) -> tuple[int, Any]:
    tok = _api_key()
    if not tok:
        return 0, _auth_error()
    if not path.startswith("/"):
        path = "/" + path
    url = urljoin(_base_url() + "/", path.lstrip("/"))
    try:
        with httpx.Client(timeout=timeout) as client:
            r = client.request(
                method,
                url,
                headers=_headers(tok),
                params=params,
                json=json_body,
            )
    except httpx.HTTPError as e:
        return 0, {"ok": False, "error": f"http error: {e}", "url": url}
    try:
        data = r.json() if r.content else None
    except json.JSONDecodeError:
        data = {"raw": (r.text or "")[:4000]}
    if r.status_code >= 400:
        msg = None
        if isinstance(data, dict):
            msg = data.get("detail") or data.get("message") or data.get("error")
        return r.status_code, {
            "ok": False,
            "status": r.status_code,
            "error": msg or r.reason_phrase or "request failed",
            "response": data if isinstance(data, dict) else str(data)[:500],
            "url": url,
        }
    return r.status_code, data


def _git_remote_https(workspace_path: str) -> str | None:
    try:
        proc = subprocess.run(
            ["git", "-C", workspace_path, "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    url = (proc.stdout or "").strip()
    if url.startswith("http://") or url.startswith("https://"):
        return url
    if url.startswith("git@"):
        # git@github.com:org/repo.git → https://github.com/org/repo.git
        if ":" in url and "@" in url:
            host_path = url.split("@", 1)[1]
            host, path_part = host_path.split(":", 1)
            return f"https://{host}/{path_part}"
    return None


def _resolve_repo_url(arguments: dict[str, Any], context: dict | None) -> str | None:
    for key in ("repo_url", "repository_url", "git_url", "url"):
        v = arguments.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
    ws = (context or {}).get("workspace") if context else None
    if isinstance(ws, dict):
        gu = ws.get("git_url")
        if isinstance(gu, str) and gu.strip():
            return gu.strip()
        rp = ws.get("path") or ws.get("repo_path")
        if isinstance(rp, str) and rp.strip():
            found = _git_remote_https(rp.strip())
            if found:
                return found
    return None


def _normalize_scan_list(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    if isinstance(data, dict):
        for key in ("items", "scans", "results", "data"):
            chunk = data.get(key)
            if isinstance(chunk, list):
                return [x for x in chunk if isinstance(x, dict)]
    return []


def _normalize_findings(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list):
        raw = data
    elif isinstance(data, dict):
        raw = None
        for key in ("findings", "items", "results", "issues", "vulnerabilities"):
            chunk = data.get(key)
            if isinstance(chunk, list):
                raw = chunk
                break
        if raw is None:
            raw = []
    else:
        raw = []
    out: list[dict[str, Any]] = []
    for it in raw[:MAX_FINDINGS]:
        if not isinstance(it, dict):
            continue
        out.append(
            {
                "id": it.get("id"),
                "rule_id": it.get("rule_id") or it.get("check_id") or it.get("rule"),
                "severity": it.get("severity") or it.get("level"),
                "path": it.get("path") or it.get("file") or it.get("location"),
                "line": it.get("line") or it.get("start_line"),
                "message": it.get("message") or it.get("title") or it.get("description"),
                "fix_hint": it.get("fix_hint") or it.get("remediation"),
            }
        )
    return out


def security_scan_list(arguments: dict[str, Any], context: dict | None = None) -> str:
    _ = context
    limit = min(max(int(arguments.get("limit") or 10), 1), 50)
    status, data = _request("GET", "/api/v1/scans/", params={"limit": limit})
    if isinstance(data, dict) and data.get("ok") is False:
        return json.dumps(data, ensure_ascii=False)
    scans = _normalize_scan_list(data)
    return json.dumps(
        {"ok": True, "base_url": _base_url(), "count": len(scans), "scans": scans},
        ensure_ascii=False,
        default=str,
    )


def security_scan_start(arguments: dict[str, Any], context: dict | None = None) -> str:
    repo_url = _resolve_repo_url(arguments, context)
    if not repo_url:
        return json.dumps(
            {
                "ok": False,
                "error": (
                    "repo_url is required (or bind a workspace with git_url / origin remote). "
                    'Example: {"repo_url": "https://github.com/org/repo.git", "branch": "main"}'
                ),
            },
            ensure_ascii=False,
        )
    body: dict[str, Any] = {"repo_url": repo_url}
    branch = str(arguments.get("branch") or arguments.get("ref") or "").strip()
    if branch:
        body["branch"] = branch
    for opt in ("scan_type", "name", "callback_url"):
        v = arguments.get(opt)
        if v is not None and str(v).strip():
            body[opt] = str(v).strip()
    status, data = _request("POST", "/api/v1/scans/", json_body=body, timeout=180.0)
    if isinstance(data, dict) and data.get("ok") is False:
        return json.dumps(data, ensure_ascii=False)
    scan_id = None
    if isinstance(data, dict):
        scan_id = data.get("id") or data.get("scan_id")
    return json.dumps(
        {
            "ok": True,
            "status_code": status,
            "scan_id": scan_id,
            "repo_url": repo_url,
            "branch": branch or None,
            "scan": data,
            "next_steps": [
                "Poll security_scan_get(scan_id) until status is completed.",
                "Then security_scan_findings(scan_id) for structured issues.",
            ],
        },
        ensure_ascii=False,
        default=str,
    )


def security_scan_get(arguments: dict[str, Any], context: dict | None = None) -> str:
    _ = context
    scan_id = str(arguments.get("scan_id") or arguments.get("id") or "").strip()
    if not scan_id:
        return json.dumps({"ok": False, "error": "scan_id is required"}, ensure_ascii=False)
    status, data = _request("GET", f"/api/v1/scans/{scan_id}")
    if isinstance(data, dict) and data.get("ok") is False:
        return json.dumps(data, ensure_ascii=False)
    st = data.get("status") if isinstance(data, dict) else None
    return json.dumps(
        {"ok": True, "status_code": status, "scan_id": scan_id, "status": st, "scan": data},
        ensure_ascii=False,
        default=str,
    )


def security_scan_findings(arguments: dict[str, Any], context: dict | None = None) -> str:
    _ = context
    scan_id = str(arguments.get("scan_id") or arguments.get("id") or "").strip()
    if not scan_id:
        return json.dumps({"ok": False, "error": "scan_id is required"}, ensure_ascii=False)
    status, data = _request("GET", f"/api/v1/scans/{scan_id}/findings")
    if isinstance(data, dict) and data.get("ok") is False and status == 404:
        status, data = _request("GET", f"/api/v1/scans/{scan_id}")
    if isinstance(data, dict) and data.get("ok") is False:
        return json.dumps(data, ensure_ascii=False)
    findings = _normalize_findings(data)
    return json.dumps(
        {
            "ok": True,
            "scan_id": scan_id,
            "finding_count": len(findings),
            "findings": findings,
            "truncated": len(findings) >= MAX_FINDINGS,
        },
        ensure_ascii=False,
    )


HANDLERS: dict[str, Callable[..., str]] = {
    "security_scan_list": security_scan_list,
    "security_scan_start": security_scan_start,
    "security_scan_get": security_scan_get,
    "security_scan_findings": security_scan_findings,
}

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "security_scan_list",
            "TOOL_DESCRIPTION": "List recent SimpleSecCheck scans for the authenticated account.",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "TOOL_DESCRIPTION": "Max scans to return (1–50, default 10)",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "security_scan_start",
            "TOOL_DESCRIPTION": (
                "Start a new security scan for a Git repository URL. "
                "Uses workspace git_url/origin when repo_url omitted."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "repo_url": {
                        "type": "string",
                        "TOOL_DESCRIPTION": "HTTPS Git clone URL (e.g. https://github.com/org/repo.git)",
                    },
                    "branch": {
                        "type": "string",
                        "TOOL_DESCRIPTION": "Branch name (optional)",
                    },
                    "scan_type": {
                        "type": "string",
                        "TOOL_DESCRIPTION": "Optional scan profile if supported by the server",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "security_scan_get",
            "TOOL_DESCRIPTION": "Get scan status and metadata by scan_id.",
            "parameters": {
                "type": "object",
                "properties": {
                    "scan_id": {"type": "string", "TOOL_DESCRIPTION": "Scan UUID or id from security_scan_start"},
                },
                "required": ["scan_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "security_scan_findings",
            "TOOL_DESCRIPTION": (
                "Fetch normalized findings for a completed scan (severity, path, rule_id, message)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "scan_id": {"type": "string", "TOOL_DESCRIPTION": "Scan id from security_scan_start"},
                },
                "required": ["scan_id"],
            },
        },
    },
]
