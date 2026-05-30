"""Shared SimpleSecCheck (scan.fr4iser.com) HTTP client and helpers — no tools exported."""

from __future__ import annotations

import json
import os
import subprocess
from typing import Any
from urllib.parse import parse_qs, urljoin, urlparse

import httpx

from apps.backend.domain.identity import get_identity
from apps.backend.infrastructure.db import db

USER_SECRET_KEY = "ssc_api_key"
DEFAULT_BASE_URL = "https://scan.fr4iser.com"
HTTP_TIMEOUT = 120.0
DEFAULT_FINDINGS_LIMIT = 50
MAX_FINDINGS_LIMIT = 200

END_RUN_GUIDANCE = (
    "End this agent run now — do not call status/findings again in the same session. "
    "When the scan may be done (~6+ min), start a new run and call security_scan_status once."
)

NO_WAIT_SUFFIX = " Returns immediately; never poll or sleep in the same agent run."

TOOL_SECRETS_REQUIRED = (USER_SECRET_KEY,)
TOOL_USER_SECRET_FORMS: dict[str, dict[str, Any]] = {
    USER_SECRET_KEY: {
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


def parse_token(raw: str) -> str:
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


def api_key() -> str | None:
    _tid, uid = get_identity()
    if uid is not None:
        raw = db.user_secret_get_plaintext(uid, USER_SECRET_KEY)
        if raw:
            t = parse_token(raw)
            if t:
                return t
    env_t = os.environ.get("SSC_API_KEY", "").strip()
    return env_t or None


def base_url() -> str:
    env_b = os.environ.get("SSC_BASE_URL", "").strip().rstrip("/")
    if env_b:
        return env_b
    return DEFAULT_BASE_URL


def auth_error() -> dict[str, Any]:
    return {
        "ok": False,
        "error": (
            f"No SimpleSecCheck API key: use request_user_secret(service_key={USER_SECRET_KEY!r}) in Web UI, "
            f"save_user_secret when pasted in chat, or Settings → Connections. "
            "Operator may set SSC_API_KEY in docker/.env (not via agent file edits). "
            '(plain token or JSON {"token":"…"}).'
        ),
    }


def _headers(tok: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {tok}",
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "agentlayer-simple-sec-check-tool",
    }


def request(
    method: str,
    path: str,
    *,
    params: dict[str, Any] | None = None,
    json_body: dict[str, Any] | None = None,
    timeout: float = HTTP_TIMEOUT,
) -> tuple[int, Any]:
    tok = api_key()
    if not tok:
        return 0, auth_error()
    if not path.startswith("/"):
        path = "/" + path
    url = urljoin(base_url() + "/", path.lstrip("/"))
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
        out: dict[str, Any] = {
            "ok": False,
            "status": r.status_code,
            "error": msg or r.reason_phrase or "request failed",
            "response": data if isinstance(data, dict) else str(data)[:500],
            "url": url,
        }
        if r.status_code == 409:
            out["retry_later"] = True
            out["agent_guidance"] = [END_RUN_GUIDANCE]
        return r.status_code, out
    return r.status_code, data


def split_path_query(path: str) -> tuple[str, dict[str, Any]]:
    p = (path or "").strip()
    if not p:
        return "", {}
    if p.startswith("http://") or p.startswith("https://"):
        parsed = urlparse(p)
        q = {k: v[0] for k, v in parse_qs(parsed.query).items() if v}
        return parsed.path or "/", q
    if "?" in p:
        base, qs = p.split("?", 1)
        q = {k: v[0] for k, v in parse_qs(qs).items() if v}
        return base, q
    return p, {}


def git_remote_https(workspace_path: str) -> str | None:
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
        if ":" in url and "@" in url:
            host_path = url.split("@", 1)[1]
            host, path_part = host_path.split(":", 1)
            return f"https://{host}/{path_part}"
    return None


def resolve_repo_url(arguments: dict[str, Any], context: dict | None) -> str | None:
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
            found = git_remote_https(rp.strip())
            if found:
                return found
    return None


def bool_arg(arguments: dict[str, Any], key: str, default: bool) -> bool:
    v = arguments.get(key)
    if v is None:
        return default
    if isinstance(v, bool):
        return v
    s = str(v).strip().lower()
    if s in ("1", "true", "yes", "on"):
        return True
    if s in ("0", "false", "no", "off"):
        return False
    return default


def findings_query_params(arguments: dict[str, Any]) -> dict[str, Any]:
    params: dict[str, Any] = {}
    if arguments.get("limit") is not None:
        lim = min(max(int(arguments["limit"]), 1), MAX_FINDINGS_LIMIT)
        params["limit"] = lim
    if arguments.get("offset") is not None:
        params["offset"] = max(int(arguments["offset"]), 0)
    sev = arguments.get("findings_severity") or arguments.get("severity")
    if sev is not None and str(sev).strip():
        params["severity"] = str(sev).strip()
    return params


def normalize_scan_list(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    if isinstance(data, dict):
        for key in ("items", "scans", "results", "data"):
            chunk = data.get(key)
            if isinstance(chunk, list):
                return [x for x in chunk if isinstance(x, dict)]
    return []


def normalize_findings(data: Any, *, cap: int | None = None) -> list[dict[str, Any]]:
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
    limit = cap if cap is not None else MAX_FINDINGS_LIMIT
    out: list[dict[str, Any]] = []
    for it in raw[:limit]:
        if not isinstance(it, dict):
            continue
        out.append(
            {
                "tool": it.get("tool"),
                "rule_id": it.get("rule_id") or it.get("check_id") or it.get("rule"),
                "severity": it.get("severity") or it.get("level"),
                "path": it.get("path") or it.get("file") or it.get("location"),
                "line": it.get("line") or it.get("start_line"),
                "message": it.get("message") or it.get("title") or it.get("description"),
                "cwe": it.get("cwe"),
                "fix_hint": it.get("fix_hint") or it.get("remediation"),
            }
        )
    return out


def ssc_status(data: dict[str, Any] | None) -> str | None:
    if not isinstance(data, dict):
        return None
    st = data.get("status")
    return str(st).strip().lower() if st is not None else None


def agent_guidance_for_status(st: str | None) -> list[str]:
    if st in ("started", "scanning", "queued", "running", "pending"):
        return [END_RUN_GUIDANCE]
    if st == "ready":
        return [
            "Findings may be in this response. For more pages use security_scan_findings "
            "with offset or pagination.next_path — then end the run."
        ]
    if st in ("completed",):
        return [
            "Scan complete. Use security_scan_findings(scan_id) for paginated issues, then end the run."
        ]
    if st in ("failed", "cancelled", "error"):
        return ["Scan did not succeed; report status to the user and end the run."]
    return []


def dump_ok(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, default=str)


def ssc_domain_attrs() -> dict[str, Any]:
    """Shared router / agent domain metadata for each tool module."""
    return {
        "TOOL_BUCKET": "network",
        "TOOL_DOMAIN": "security_scan",
        "TOOL_CAPABILITIES": ("security.scan",),
        "TOOL_SECRETS_REQUIRED": TOOL_SECRETS_REQUIRED,
        "TOOL_USER_SECRET_FORMS": TOOL_USER_SECRET_FORMS,
    }
