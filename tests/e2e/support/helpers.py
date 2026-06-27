"""Shared helpers for HTTP E2E journeys against a running Agent Layer instance."""

from __future__ import annotations

import os
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

import httpx

REPO_ROOT = Path(__file__).resolve().parents[3]
AGENTLAYER_SELF_NAME = "agentlayer-self"
E2E_GIT_WORKSPACE_NAME = "e2e-agentlayer-git"
SHARE_RESOURCE_GOOGLE_CALENDAR = "google_calendar"


def load_dotenv(path: Path) -> None:
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = val


def load_e2e_env() -> None:
    load_dotenv(REPO_ROOT / ".env")
    load_dotenv(REPO_ROOT / ".env.e2e")


def _candidate_local_ports() -> list[str]:
    ports: list[str] = []
    for key in ("AGENT_INTERNAL_HTTP_PORT", "UVICORN_PORT"):
        p = (os.environ.get(key) or "").strip()
        if p:
            ports.append(p)
    ports.append("8080")
    host_port = (os.environ.get("AGENT_HTTP_PORT") or "").strip()
    if host_port:
        ports.append(host_port)
    ports.append("8088")
    seen: set[str] = set()
    out: list[str] = []
    for p in ports:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


def _local_health_ok(url: str, *, timeout: float = 1.5) -> bool:
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.get(f"{url.rstrip('/')}/health")
        return resp.status_code == 200
    except Exception:
        return False


def resolve_local_agent_base_url() -> str:
    """
    Base URL for in-process benchmarks / E2E against localhost.

    Prefers AGENT_BENCH_BASE_URL, then probes common listen ports (8080 in Docker,
    AGENT_HTTP_PORT / 8088 on host dev), then AGENT_E2E_BASE_URL from .env.
    """
    bench = (os.environ.get("AGENT_BENCH_BASE_URL") or "").strip().rstrip("/")
    if bench:
        return bench
    for port in _candidate_local_ports():
        url = f"http://127.0.0.1:{port}"
        if _local_health_ok(url):
            return url
    explicit = (os.environ.get("AGENT_E2E_BASE_URL") or "").strip().rstrip("/")
    if explicit:
        return explicit
    port = (os.environ.get("AGENT_HTTP_PORT") or "8088").strip()
    return f"http://127.0.0.1:{port}"


def base_url() -> str:
    return resolve_local_agent_base_url()


def ws_url(token: str) -> str:
    http = base_url()
    if http.startswith("https://"):
        scheme = "wss://"
        host = http[len("https://") :]
    else:
        scheme = "ws://"
        host = http[len("http://") :] if http.startswith("http://") else http
    return f"{scheme}{host}/ws/v1/chat?token={token}"


def admin_credentials() -> tuple[str, str]:
    email = (
        os.environ.get("AGENT_E2E_EMAIL")
        or os.environ.get("AGENT_TEST_EMAIL")
        or os.environ.get("AGENT_INITIAL_ADMIN_EMAIL")
        or ""
    ).strip()
    password = (
        os.environ.get("AGENT_E2E_PASSWORD")
        or os.environ.get("AGENT_TEST_PASSWORD")
        or os.environ.get("AGENT_INITIAL_ADMIN_PASSWORD")
        or ""
    ).strip()
    if not email or not password:
        raise RuntimeError(
            "Missing admin credentials (AGENT_E2E_EMAIL/PASSWORD or AGENT_INITIAL_ADMIN_* in .env)"
        )
    return email, password


def user_b_credentials() -> tuple[str, str]:
    email = (os.environ.get("AGENT_E2E_EMAIL_B") or "").strip()
    password = os.environ.get("AGENT_E2E_PASSWORD_B") or ""
    if not email or not password:
        raise RuntimeError("Missing User B credentials (AGENT_E2E_EMAIL_B / AGENT_E2E_PASSWORD_B)")
    return email, password


def git_clone_url() -> str:
    return (
        os.environ.get("AGENT_E2E_GIT_URL")
        or "https://github.com/octocat/Hello-World.git"
    ).strip()


def env_truthy(name: str) -> bool:
    return (os.environ.get(name) or "").strip().lower() in ("1", "true", "yes", "on")


@dataclass
class E2EClient:
    http: httpx.Client
    token: str
    user_id: str
    role: str
    email: str

    @classmethod
    def login(cls, email: str, password: str, *, timeout: float = 60.0) -> E2EClient:
        base = base_url()
        with httpx.Client(base_url=base, timeout=timeout) as tmp:
            resp = tmp.post("/auth/login", json={"email": email, "password": password})
            resp.raise_for_status()
            payload = resp.json()
        token = str(payload.get("access_token") or "")
        user = payload.get("user") or {}
        if not token:
            raise RuntimeError("login response missing access_token")
        http = httpx.Client(
            base_url=base,
            headers={"Authorization": f"Bearer {token}"},
            timeout=timeout,
        )
        return cls(
            http=http,
            token=token,
            user_id=str(user.get("id") or ""),
            role=str(user.get("role") or "user"),
            email=str(user.get("email") or email),
        )

    @classmethod
    def for_user_id(cls, user_id: uuid.UUID | str, *, timeout: float = 60.0) -> E2EClient:
        """Mint a JWT for an existing user (in-process benchmark runner / same DB)."""
        from apps.backend.infrastructure.identity.auth import create_access_token, get_user_by_id

        uid = uuid.UUID(str(user_id))
        user = get_user_by_id(uid)
        if not user:
            raise RuntimeError(f"user not found: {user_id}")
        token = create_access_token(user.id, user.role)
        http = httpx.Client(
            base_url=base_url(),
            headers={"Authorization": f"Bearer {token}"},
            timeout=timeout,
        )
        return cls(
            http=http,
            token=token,
            user_id=str(user.id),
            role=str(user.role or "user"),
            email=str(user.email or ""),
        )

    def close(self) -> None:
        self.http.close()

    def get_json(self, path: str, **params: Any) -> dict[str, Any]:
        resp = self.http.get(path, params=params or None)
        resp.raise_for_status()
        data = resp.json()
        assert isinstance(data, dict)
        return data

    def post_json(self, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        resp = self.http.post(path, json=body or {})
        resp.raise_for_status()
        data = resp.json()
        assert isinstance(data, dict)
        return data

    def patch_json(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        resp = self.http.patch(path, json=body)
        resp.raise_for_status()
        data = resp.json()
        assert isinstance(data, dict)
        return data

    def post_json_allow(self, path: str, body: dict[str, Any], *, ok: set[int]) -> httpx.Response:
        resp = self.http.post(path, json=body)
        if resp.status_code not in ok:
            resp.raise_for_status()
        return resp


def require_server() -> None:
    url = f"{base_url()}/health"
    try:
        with httpx.Client(timeout=5.0) as client:
            resp = client.get(url)
            resp.raise_for_status()
    except Exception as exc:
        raise RuntimeError(f"Agent Layer not reachable at {url}: {exc}") from exc


def operator_self_editing_enabled(client: E2EClient) -> bool:
    settings = client.get_json("/v1/admin/operator-settings")
    return bool(settings.get("workspace_allow_self_editing", False))


@contextmanager
def temporary_self_editing_enabled(client: E2EClient) -> Iterator[bool]:
    """
    Enable ``workspace_allow_self_editing`` for E2E when off; restore previous value on exit.

    Requires an admin client. Yields the prior flag (before any change).
    """
    if client.role != "admin":
        raise RuntimeError("admin role required to patch operator settings")
    prev = operator_self_editing_enabled(client)
    if not prev:
        client.patch_json(
            "/v1/admin/operator-settings",
            {"workspace_allow_self_editing": True},
        )
    try:
        yield prev
    finally:
        if not prev:
            client.patch_json(
                "/v1/admin/operator-settings",
                {"workspace_allow_self_editing": False},
            )


def find_workspace_by_name(client: E2EClient, name: str) -> dict[str, Any] | None:
    data = client.get_json("/v1/workspaces")
    for ws in data.get("workspaces") or []:
        if isinstance(ws, dict) and (ws.get("name") or "").strip() == name:
            return ws
    return None


def ensure_git_workspace(client: E2EClient, *, name: str, git_url: str) -> dict[str, Any]:
    existing = find_workspace_by_name(client, name)
    if existing:
        return existing
    data = client.post_json(
        "/v1/workspaces",
        {
            "name": name,
            "source": "git",
            "git_url": git_url,
            "git_branch": "master",
        },
    )
    ws = data.get("workspace")
    assert isinstance(ws, dict), data
    return ws


def ensure_user_b(client: E2EClient) -> E2EClient:
    """Create User B via admin API when missing; return logged-in User B client."""
    email_b, password_b = user_b_credentials()
    try:
        return E2EClient.login(email_b, password_b)
    except httpx.HTTPStatusError:
        pass

    if client.role != "admin":
        raise RuntimeError("User B missing and current user is not admin — cannot create User B")

    resp = client.post_json_allow(
        "/v1/admin/users",
        {"email": email_b, "password": password_b, "role": "user", "tenant_id": 1},
        ok={200, 201, 409},
    )
    if resp.status_code == 409:
        # Already exists but password may differ — caller must fix env.
        return E2EClient.login(email_b, password_b)
    return E2EClient.login(email_b, password_b)


def wait_index_idle(client: E2EClient, workspace_id: str, *, timeout_s: float = 120.0) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_s
    last: dict[str, Any] = {}
    while time.monotonic() < deadline:
        data = client.get_json(f"/v1/workspaces/{workspace_id}/index/status")
        last = data
        status = data.get("status") if isinstance(data.get("status"), dict) else data
        phase = (status.get("phase") or status.get("index_phase") or "").lower()
        running = bool(status.get("running") or status.get("index_running"))
        if not running and phase not in ("running", "indexing", "queued"):
            return data
        time.sleep(2.0)
    return last


def sample_agent_log_v2() -> dict[str, Any]:
    sub_id = uuid.uuid4().hex[:8]
    return {
        "v": 2,
        "current": [
            {"id": f"sa-{sub_id}", "kind": "subagent_start", "text": "coding", "subagentAgentId": "coding"},
            {
                "id": f"sd-{sub_id}",
                "kind": "subagent_done",
                "text": "Done",
                "subagentAgentId": "coding",
                "durationMs": 1200,
            },
        ],
        "turns": [],
    }
