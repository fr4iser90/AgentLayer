"""Unit tests for the UX-audit seed's ``main()`` orchestration.

``main()`` is the entry point ``validate_stack.sh`` runs. Its value is not the
happy path but the four post-create guards: they are what turn a silently
half-projected dashboard into a loud failure. Those guards were previously only
exercised by a live run, so a regression in one of them would pass unit tests and
only surface as a broken audit board.

The real ``httpx.Client`` is swapped for a MockTransport that answers the whole
seed conversation, and ``OUT_META`` is redirected into ``tmp_path``.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import httpx
import pytest

REPO = Path(__file__).resolve().parents[2]
SEED_PATH = REPO / "scripts" / "seed_dashboard_ux_audit.py"

_REAL_CLIENT = httpx.Client

PROJECTED_OK = {
    "items": [{"id": "r_ship", "done": True}],
    "notes": "## Demo notes",
    "kpi": {"value": "42", "trend": "up"},
    "timeline": [{"id": "t1", "date": "2026-09-01", "note": "Kickoff"}],
}


@pytest.fixture(scope="module")
def mod():
    spec = importlib.util.spec_from_file_location("seed_dashboard_ux_audit_main", SEED_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SeedApi:
    """Answers the full seed conversation, recording every request."""

    def __init__(self, *, projected=None, source_id="src-dash-1", audit_id="audit-dash-2",
                 scheduler_rows=None):
        self.projected = PROJECTED_OK if projected is None else projected
        self.source_id = source_id
        self.audit_id = audit_id
        self.scheduler_rows = (
            [{"id": "j1", "dashboard_id": audit_id}] if scheduler_rows is None else scheduler_rows
        )
        self.calls: list[tuple[str, str, dict | None]] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else None
        path = request.url.path
        self.calls.append((request.method, path, body))

        if (request.method, path) == ("POST", "/auth/login"):
            return httpx.Response(200, json={"access_token": "t", "user": {"id": "admin-1"}})
        if (request.method, path) == ("GET", "/v1/dashboards/install-status"):
            return httpx.Response(200, json={"schema_installed": True})
        if (request.method, path) == ("GET", "/v1/dashboards"):
            return httpx.Response(200, json={"dashboards": []})
        if (request.method, path) == ("POST", "/v1/dashboards"):
            title = (body or {}).get("title", "")
            new_id = self.source_id if "Ref Source" in title else self.audit_id
            return httpx.Response(201, json={"dashboard": {"id": new_id, "title": title}})
        if request.method == "GET" and path.startswith("/v1/dashboards/"):
            return httpx.Response(200, json={"dashboard": {"id": self.audit_id, "data": self.projected}})
        if (request.method, path) == ("GET", "/v1/user/scheduler-jobs"):
            return httpx.Response(200, json={"jobs": self.scheduler_rows})
        if (request.method, path) == ("POST", "/v1/user/scheduler-jobs"):
            return httpx.Response(201, json={"job": {"id": "job-created"}})
        return httpx.Response(404, json={"detail": f"unhandled {request.method} {path}"})

    def posted_dashboard_titles(self) -> list[str]:
        return [c[2]["title"] for c in self.calls if c[0] == "POST" and c[1] == "/v1/dashboards"]


@pytest.fixture
def seed_env(monkeypatch, tmp_path, mod):
    """Wire main() against a mock API with no live server and no repo writes."""
    state: dict = {"api": SeedApi()}

    def install(api: SeedApi):
        state["api"] = api

        def factory(*args, **kwargs):
            kwargs.pop("base_url", None)
            return _REAL_CLIENT(
                transport=httpx.MockTransport(api.handler), base_url="http://testserver", **kwargs
            )

        monkeypatch.setattr(mod.httpx, "Client", factory)
        monkeypatch.setattr(mod, "load_e2e_env", lambda *a, **k: None)
        monkeypatch.setattr(mod, "base_url", lambda: "http://testserver")
        monkeypatch.setattr(mod, "admin_credentials", lambda: ("admin@example.com", "pw"))
        monkeypatch.setattr(mod, "_ensure_friend_for_share", lambda client, **kw: "friend-1")
        meta = tmp_path / "dashboard.json"
        monkeypatch.setattr(mod, "OUT_META", meta)
        return meta

    return install


def test_main_returns_zero_and_writes_meta(seed_env, mod):
    meta_path = seed_env(SeedApi())
    assert mod.main() == 0
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    assert meta["dashboard_id"] == "audit-dash-2"
    assert meta["source_dashboard_id"] == "src-dash-1"
    assert meta["friend_user_id"] == "friend-1"
    assert meta["title"] == mod.TITLE
    assert meta["url"] == "http://testserver/app/dashboard?id=audit-dash-2"
    assert meta["scheduler_jobs"] == 1
    assert len(meta["blocks"]) == 18
    assert {"id", "type"} <= set(meta["blocks"][0])


def test_main_creates_source_before_audit_dashboard(seed_env, mod):
    api = SeedApi()
    seed_env(api)
    mod.main()
    titles = api.posted_dashboard_titles()
    assert titles == ["UX Audit — Ref Source", mod.TITLE], "source must exist before the ref points at it"


def test_main_passes_real_source_id_into_the_ref_block(seed_env, mod):
    api = SeedApi(source_id="real-src-99")
    seed_env(api)
    mod.main()
    audit_post = [c for c in api.calls if c[0] == "POST" and c[1] == "/v1/dashboards"][-1]
    blocks = audit_post[2]["ui_layout"]["blocks"]
    ref = next(b for b in blocks if b["id"] == "demo-ref")
    assert ref["props"]["sourceDashboardId"] == "real-src-99"
    assert ref["props"]["sourceBlockId"] == "src-md"


def test_main_raises_when_source_dashboard_has_no_id(seed_env, mod):
    seed_env(SeedApi(source_id=""))
    with pytest.raises(RuntimeError, match="failed to create source dashboard"):
        mod.main()


def test_main_raises_when_audit_dashboard_has_no_id(seed_env, mod):
    seed_env(SeedApi(audit_id=""))
    with pytest.raises(RuntimeError, match="failed to create audit dashboard"):
        mod.main()


def test_main_raises_when_demo_data_did_not_project(seed_env, mod):
    seed_env(SeedApi(projected={}))
    with pytest.raises(RuntimeError, match="demo data did not project after create"):
        mod.main()


def test_main_raises_when_timeline_fields_missing(seed_env, mod):
    projected = dict(PROJECTED_OK)
    projected["timeline"] = [{"id": "t1"}]  # no date / note
    seed_env(SeedApi(projected=projected))
    with pytest.raises(RuntimeError, match="timeline demo fields missing"):
        mod.main()


def test_main_raises_when_kpi_trend_missing(seed_env, mod):
    projected = dict(PROJECTED_OK)
    projected["kpi"] = {"value": "42"}  # trend absent
    seed_env(SeedApi(projected=projected))
    with pytest.raises(RuntimeError, match="kpi trend demo missing"):
        mod.main()


def test_main_raises_when_scheduler_jobs_absent(seed_env, mod):
    seed_env(SeedApi(scheduler_rows=[]))
    with pytest.raises(RuntimeError, match="scheduler demo jobs missing after seed"):
        mod.main()


def test_main_meta_projects_sorted_keys(seed_env, mod):
    meta_path = seed_env(SeedApi())
    mod.main()
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    assert meta["projected_keys"] == sorted(meta["projected_keys"])
    assert "items" in meta["projected_keys"]
