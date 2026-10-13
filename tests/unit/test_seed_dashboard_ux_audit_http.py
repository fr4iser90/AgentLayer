"""Unit tests for the HTTP layer of the UX-audit seed.

These functions drive the live API during ``validate_stack.sh``'s seed stage and had
no test at all: a wrong endpoint, a wrong payload key, or a mis-handled status code
surfaced as a half-seeded board several stages later.

``httpx.MockTransport`` records every request, so each test asserts both the
branch taken and the exact request the seed would have sent.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import httpx
import pytest

REPO = Path(__file__).resolve().parents[2]
SEED_PATH = REPO / "scripts" / "seed_dashboard_ux_audit.py"


@pytest.fixture(scope="module")
def mod():
    spec = importlib.util.spec_from_file_location("seed_dashboard_ux_audit_http", SEED_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Recorder:
    """MockTransport handler backed by a {method+path: (status, json)} table."""

    def __init__(self, routes: dict[str, tuple[int, dict]]):
        self.routes = routes
        self.calls: list[tuple[str, str, dict | None]] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else None
        self.calls.append((request.method, request.url.path, body))
        key = f"{request.method} {request.url.path}"
        status, payload = self.routes.get(key, (200, {}))
        return httpx.Response(status, json=payload)

    def client(self) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(self.handler), base_url="http://test")

    def paths(self) -> list[str]:
        return [f"{m} {p}" for m, p, _ in self.calls]


HEADERS = {"Authorization": "Bearer admin-token"}


# ------------------------------------------------------------------ _ensure_schema
def test_ensure_schema_skips_install_when_already_installed(mod):
    rec = Recorder({"GET /v1/dashboards/install-status": (200, {"schema_installed": True})})
    with rec.client() as client:
        mod._ensure_schema(client, HEADERS)
    assert rec.paths() == ["GET /v1/dashboards/install-status"]


def test_ensure_schema_installs_first_offered_kind(mod):
    rec = Recorder(
        {
            "GET /v1/dashboards/install-status": (
                200,
                {"schema_installed": False, "schema_install_offers": [{"kind": "crm"}, {"kind": "ops"}]},
            ),
            "POST /v1/dashboards/install": (200, {"ok": True}),
        }
    )
    with rec.client() as client:
        mod._ensure_schema(client, HEADERS)
    assert rec.paths() == ["GET /v1/dashboards/install-status", "POST /v1/dashboards/install"]
    assert rec.calls[-1][2] == {"kinds": ["crm"]}, "must install only the first offered kind"


def test_ensure_schema_falls_back_to_custom_when_no_offers(mod):
    rec = Recorder(
        {
            "GET /v1/dashboards/install-status": (200, {"schema_installed": False}),
            "POST /v1/dashboards/install": (200, {"ok": True}),
        }
    )
    with rec.client() as client:
        mod._ensure_schema(client, HEADERS)
    assert rec.calls[-1][2] == {"kinds": ["custom"]}


# ----------------------------------------------------------------------- _login_as
def test_login_as_returns_headers_and_uid(mod):
    rec = Recorder(
        {
            "POST /auth/login": (
                200,
                {"access_token": "tok-123", "user": {"id": 4242}},
            )
        }
    )
    with rec.client() as client:
        headers, uid = mod._login_as(client, "a@b.c", "pw")
    assert headers == {"Authorization": "Bearer tok-123"}
    assert uid == "4242", "uid must be stringified"


def test_login_as_accepts_token_alias(mod):
    rec = Recorder({"POST /auth/login": (200, {"token": "tok-alt", "user": {"id": "7"}})})
    with rec.client() as client:
        headers, uid = mod._login_as(client, "a@b.c", "pw")
    assert headers["Authorization"] == "Bearer tok-alt"
    assert uid == "7"


def test_login_as_raises_without_token(mod):
    rec = Recorder({"POST /auth/login": (200, {"user": {"id": "7"}})})
    with rec.client() as client:
        with pytest.raises(RuntimeError, match="login missing token"):
            mod._login_as(client, "a@b.c", "pw")


def test_login_as_raises_without_user_id(mod):
    rec = Recorder({"POST /auth/login": (200, {"access_token": "t"})})
    with rec.client() as client:
        with pytest.raises(RuntimeError, match="login missing user id"):
            mod._login_as(client, "a@b.c", "pw")


# ----------------------------------------------------------------- _delete_by_title
def test_delete_by_title_removes_only_the_match(mod):
    rec = Recorder(
        {
            "GET /v1/dashboards": (
                200,
                {
                    "dashboards": [
                        {"id": "d1", "title": "UX Audit — All Blocks"},
                        {"id": "d2", "title": "Something else"},
                        {"id": "d3", "title": "UX Audit — All Blocks"},
                    ]
                },
            ),
            "DELETE /v1/dashboards/d1": (200, {}),
            "DELETE /v1/dashboards/d3": (200, {}),
        }
    )
    with rec.client() as client:
        mod._delete_by_title(client, HEADERS, "UX Audit — All Blocks")
    assert sorted(rec.paths()) == [
        "DELETE /v1/dashboards/d1",
        "DELETE /v1/dashboards/d3",
        "GET /v1/dashboards",
    ]


def test_delete_by_title_is_noop_without_match(mod):
    rec = Recorder({"GET /v1/dashboards": (200, {"dashboards": [{"id": "x", "title": "other"}]})})
    with rec.client() as client:
        mod._delete_by_title(client, HEADERS, "UX Audit — All Blocks")
    assert rec.paths() == ["GET /v1/dashboards"]


# ------------------------------------------------------------- _seed_scheduler_jobs
def test_seed_scheduler_jobs_skips_when_dashboard_already_has_a_job(mod):
    rec = Recorder(
        {
            "GET /v1/user/scheduler-jobs": (
                200,
                {"jobs": [{"id": "j1", "dashboard_id": "dash-1"}]},
            )
        }
    )
    with rec.client() as client:
        mod._seed_scheduler_jobs(client, HEADERS, "dash-1")
    assert rec.paths() == ["GET /v1/user/scheduler-jobs"], "must not create duplicates"


def test_seed_scheduler_jobs_creates_both_jobs_with_expected_shape(mod):
    rec = Recorder({"GET /v1/user/scheduler-jobs": (200, {"jobs": []})})
    with rec.client() as client:
        mod._seed_scheduler_jobs(client, HEADERS, "dash-new")
    posts = [c for c in rec.calls if c[0] == "POST"]
    assert len(posts) == 2
    titles = [p[2]["title"] for p in posts]
    assert titles == ["UX audit morning digest", "UX audit weekly polish check"]
    intervals = [p[2]["interval_minutes"] for p in posts]
    assert intervals == [60, 1440]
    for _, _, body in posts:
        assert body["dashboard_id"] == "dash-new"
        assert body["enabled"] is True
        assert body["execution_target"] == "general"
        assert body["instructions"].strip()


def test_seed_scheduler_jobs_ignores_other_dashboards_jobs(mod):
    rec = Recorder(
        {
            "GET /v1/user/scheduler-jobs": (
                200,
                {"jobs": [{"id": "j9", "dashboard_id": "someone-else"}]},
            )
        }
    )
    with rec.client() as client:
        mod._seed_scheduler_jobs(client, HEADERS, "dash-mine")
    assert len([c for c in rec.calls if c[0] == "POST"]) == 2


# --------------------------------------------------------- _ensure_friend_for_share
class _FakeClient:
    def __init__(self, user_id: str, token: str, email: str):
        self.user_id = user_id
        self.token = token
        self.email = email


def _patch_e2e_helpers(monkeypatch, mod):
    admin = _FakeClient("admin-1", "admin-tok", "admin@example.com")
    user_b = _FakeClient("userb-1", "userb-tok", "b@example.com")
    monkeypatch.setattr(mod, "admin_credentials", lambda: ("admin@example.com", "pw"))
    monkeypatch.setattr(mod.E2EClient, "login", staticmethod(lambda e, p: admin))
    monkeypatch.setattr(mod, "ensure_user_b", lambda c: user_b)
    return admin, user_b


def test_ensure_friend_reuses_existing_friendship(monkeypatch, mod):
    _patch_e2e_helpers(monkeypatch, mod)
    rec = Recorder(
        {
            "GET /v1/friends": (200, {"friends": [{"friend_user_id": "userb-1"}]}),
            "POST /v1/shares/set": (200, {"ok": True}),
        }
    )
    with rec.client() as client:
        got = mod._ensure_friend_for_share(
            client, admin_headers=HEADERS, admin_user_id="admin-1"
        )
    assert got == "userb-1"
    # Already friends: no request/accept round-trip, but the calendar share still lands.
    assert rec.paths() == ["GET /v1/friends", "POST /v1/shares/set"]


def test_ensure_friend_requests_and_accepts_when_not_yet_friends(monkeypatch, mod):
    _patch_e2e_helpers(monkeypatch, mod)
    rec = Recorder(
        {
            "GET /v1/friends": (200, {"friends": []}),
            "POST /v1/friends/request": (201, {"ok": True}),
            "GET /v1/friends/requests/incoming": (
                200,
                {"requests": [{"id": "req-5", "from": "admin@example.com"}]},
            ),
            "POST /v1/friends/requests/req-5/accept": (200, {"ok": True}),
            "POST /v1/shares/set": (200, {"ok": True}),
        }
    )
    with rec.client() as client:
        got = mod._ensure_friend_for_share(
            client, admin_headers=HEADERS, admin_user_id="admin-1"
        )
    assert got == "userb-1"
    assert rec.paths() == [
        "GET /v1/friends",
        "POST /v1/friends/request",
        "GET /v1/friends/requests/incoming",
        "POST /v1/friends/requests/req-5/accept",
        "POST /v1/shares/set",
    ]
    req_body = rec.calls[1][2]
    assert req_body == {"email": "b@example.com", "message": "UX audit friend"}


def test_ensure_friend_share_payload_targets_admin_and_calendar(monkeypatch, mod):
    _patch_e2e_helpers(monkeypatch, mod)
    rec = Recorder(
        {
            "GET /v1/friends": (200, {"friends": [{"friend_user_id": "userb-1"}]}),
            "POST /v1/shares/set": (200, {"ok": True}),
        }
    )
    with rec.client() as client:
        mod._ensure_friend_for_share(client, admin_headers=HEADERS, admin_user_id="admin-1")
    share_body = rec.calls[-1][2]
    assert share_body["grantee_user_id"] == "admin-1"
    assert share_body["resource_identifier"] == "primary"
    assert share_body["is_allowed"] is True
    assert share_body["resource_type"] == mod.SHARE_RESOURCE_GOOGLE_CALENDAR


def test_ensure_friend_tolerates_400_on_duplicate_share(monkeypatch, mod):
    """A pre-existing share answers 400; the seed must not abort the whole stage."""
    _patch_e2e_helpers(monkeypatch, mod)
    rec = Recorder(
        {
            "GET /v1/friends": (200, {"friends": [{"friend_user_id": "userb-1"}]}),
            "POST /v1/shares/set": (400, {"detail": "already shared"}),
        }
    )
    with rec.client() as client:
        got = mod._ensure_friend_for_share(
            client, admin_headers=HEADERS, admin_user_id="admin-1"
        )
    assert got == "userb-1"
