#!/usr/bin/env python3
"""Seed a custom dashboard with every block type filled with demo data (UX audit).

Note: PATCH /v1/dashboards ignores ``data`` (domain collections are SoT).
Demo content must be supplied on CREATE so legacy→collections import runs.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from tests.e2e.support.helpers import (  # noqa: E402
    SHARE_RESOURCE_GOOGLE_CALENDAR,
    E2EClient,
    admin_credentials,
    base_url,
    ensure_user_b,
    load_e2e_env,
)


TITLE = "UX Audit — All Blocks"
OUT_META = REPO / "example" / "dashboard-ux-audit" / "dashboard.json"


def _ensure_schema(client: httpx.Client, headers: dict) -> None:
    r = client.get("/v1/dashboards/install-status", headers=headers)
    r.raise_for_status()
    st = r.json()
    if st.get("schema_installed"):
        return
    offers = st.get("schema_install_offers") or []
    kinds = [o.get("kind") for o in offers if isinstance(o, dict) and o.get("kind")]
    if not kinds:
        kinds = ["custom"]
    r2 = client.post("/v1/dashboards/install", headers=headers, json={"kinds": kinds[:1]})
    r2.raise_for_status()


def _login_as(client: httpx.Client, email: str, password: str) -> tuple[dict, str]:
    r = client.post("/auth/login", json={"email": email, "password": password})
    r.raise_for_status()
    data = r.json()
    token = data.get("access_token") or data.get("token")
    if not token:
        raise RuntimeError(f"login missing token: {data!r}")
    user = data.get("user") or {}
    uid = str(user.get("id") or "")
    if not uid:
        raise RuntimeError(f"login missing user id: {data!r}")
    return {"Authorization": f"Bearer {token}"}, uid


def _delete_by_title(client: httpx.Client, headers: dict, title: str) -> None:
    r = client.get("/v1/dashboards", headers=headers)
    r.raise_for_status()
    for d in r.json().get("dashboards") or []:
        if str(d.get("title") or "") == title and d.get("id"):
            client.delete(f"/v1/dashboards/{d['id']}", headers=headers)


def _ensure_friend_for_share(
    client: httpx.Client, *, admin_headers: dict, admin_user_id: str
) -> str:
    """Return User B id; ensure friendship + calendar share toward admin (best-effort)."""
    email, password = admin_credentials()
    admin = E2EClient.login(email, password)
    user_b = ensure_user_b(admin)
    user_b_id = user_b.user_id
    headers_b = {"Authorization": f"Bearer {user_b.token}"}

    friends = client.get("/v1/friends", headers=admin_headers)
    friends.raise_for_status()
    already = any(
        str(f.get("friend_user_id") or f.get("user_id") or f.get("id") or "") == user_b_id
        for f in (friends.json().get("friends") or [])
        if isinstance(f, dict)
    )
    if not already:
        req = client.post(
            "/v1/friends/request",
            headers=admin_headers,
            json={"email": user_b.email, "message": "UX audit friend"},
        )
        if req.status_code not in (200, 400):
            req.raise_for_status()
        incoming = client.get("/v1/friends/requests/incoming", headers=headers_b)
        incoming.raise_for_status()
        pending = [
            r
            for r in (incoming.json().get("requests") or [])
            if isinstance(r, dict) and r.get("id")
        ]
        if pending:
            acc = client.post(
                f"/v1/friends/requests/{pending[0]['id']}/accept",
                headers=headers_b,
                json={},
            )
            acc.raise_for_status()

    # Friend owns the calendar; share it with the admin viewer of the widget.
    share = client.post(
        "/v1/shares/set",
        headers=headers_b,
        json={
            "grantee_user_id": admin_user_id,
            "resource_type": SHARE_RESOURCE_GOOGLE_CALENDAR,
            "resource_identifier": "primary",
            "is_allowed": True,
        },
    )
    if share.status_code not in (200, 400):
        share.raise_for_status()
    return user_b_id


def _seed_scheduler_jobs(client: httpx.Client, headers: dict, dashboard_id: str) -> None:
    existing = client.get(
        "/v1/user/scheduler-jobs",
        headers=headers,
        params={"dashboard_id": dashboard_id, "limit": 50},
    )
    existing.raise_for_status()
    jobs = existing.json().get("jobs") or []
    if any(str(j.get("dashboard_id") or "") == dashboard_id for j in jobs if isinstance(j, dict)):
        return
    for title, minutes, instructions in (
        (
            "UX audit morning digest",
            60,
            "Summarize open dashboard items for the UX audit board.",
        ),
        (
            "UX audit weekly polish check",
            1440,
            "List blocks that still look empty or edit-heavy on the audit board.",
        ),
    ):
        r = client.post(
            "/v1/user/scheduler-jobs",
            headers=headers,
            json={
                "execution_target": "general",
                "interval_minutes": minutes,
                "enabled": True,
                "title": title,
                "instructions": instructions,
                "dashboard_id": dashboard_id,
            },
        )
        r.raise_for_status()


def build_layout_and_data(*, source_dash_id: str, source_block_id: str, friend_user_id: str):
    y = 0

    def row(bid: str, typ: str, h: int, props: dict) -> dict:
        nonlocal y
        block = {
            "id": bid,
            "type": typ,
            "grid": {"x": 0, "y": y, "w": 12, "h": h},
            "props": props,
        }
        y += h
        return block

    # Stable public demo images (GalleryImage accepts https URLs)
    img_a = "https://picsum.photos/seed/agentlayer-ux-a/960/540"
    img_b = "https://picsum.photos/seed/agentlayer-ux-b/960/540"
    yt_embed = "https://www.youtube.com/embed/jNQXAC9IVRw"
    yt_embed_2 = "https://www.youtube.com/embed/dQw4w9WgXcQ"

    blocks = [
        row(
            "demo-table",
            "table",
            7,
            {
                "dataPath": "items",
                "title": "Demo Table",
                "columns": [
                    {"field": "done", "kind": "checkbox", "label": ""},
                    {"field": "name", "kind": "text", "label": "Item"},
                    {"field": "owner", "kind": "text", "label": "Owner"},
                    {"field": "due", "kind": "text", "label": "Due"},
                ],
            },
        ),
        row(
            "demo-markdown",
            "markdown",
            5,
            {"dataPath": "notes", "placeholder": "Notes", "title": "Markdown"},
        ),
        row(
            "demo-rich-md",
            "rich_markdown",
            7,
            {"dataPath": "rich_notes", "title": "Rich Markdown", "placeholder": "## Notes"},
        ),
        row("demo-gallery", "gallery", 8, {"dataPath": "photos", "title": "Gallery"}),
        row("demo-hero", "hero", 7, {"dataPath": "hero", "title": "Hero"}),
        row("demo-timeline", "timeline", 8, {"dataPath": "timeline", "title": "Timeline"}),
        row("demo-stat", "stat", 5, {"dataPath": "kpi", "title": "KPI"}),
        row("demo-chart", "chart", 10, {"dataPath": "chart", "title": "Chart"}),
        row("demo-spark", "sparkline", 5, {"dataPath": "spark", "title": "Sparkline"}),
        row("demo-kanban", "kanban", 12, {"dataPath": "kanban", "title": "Kanban"}),
        row("demo-embed", "embed", 10, {"dataPath": "embed", "title": "Embed"}),
        row(
            "demo-media",
            "media_player",
            9,
            {"dataPath": "media_queue", "title": "Media Player", "showQueue": True},
        ),
        row(
            "demo-section",
            "section",
            10,
            {
                "title": "Section (nested markdown)",
                "collapsed": False,
                "nested": {
                    "version": 2,
                    "blocks": [
                        {
                            "id": "demo-section-inner",
                            "type": "markdown",
                            "grid": {"x": 0, "y": 0, "w": 12, "h": 5},
                            "props": {
                                "dataPath": "section_notes",
                                "placeholder": "Nested",
                                "title": "Nested note",
                            },
                        }
                    ],
                },
            },
        ),
        row(
            "demo-cards",
            "card_grid",
            10,
            {
                "dataPath": "cards",
                "title": "Card Grid",
                "gridColumns": 3,
                "cardFields": ["title", "remote_url", "tags", "status"],
                "enableSearch": True,
                "enableRowDetail": True,
                "enableRunNow": False,
                "enableWorkspaceLink": False,
            },
        ),
        row(
            "demo-share",
            "share_widget",
            5,
            {
                "title": "Friend share (demo)",
                "resourceType": "google_calendar",
                "friendUserId": friend_user_id,
                "friendDisplayName": "Demo Friend",
                "daysAhead": 7,
            },
        ),
        row(
            "demo-formula",
            "formula_calc",
            9,
            {
                "title": "Formula Calc",
                "disclaimer": "Demo calculator — not medical advice.",
                "formulaNote": "sum = a + b; product = a * b",
                "formulaInputs": [
                    {"key": "a", "label": "Value A", "defaultValue": 12},
                    {"key": "b", "label": "Value B", "defaultValue": 5},
                ],
                "formulaOutputs": [
                    {"key": "sum", "label": "Sum", "expr": "a+b"},
                    {"key": "product", "label": "Product", "expr": "a*b"},
                ],
            },
        ),
        row(
            "demo-ref",
            "dashboard_ref",
            6,
            {
                "title": "Pinned ref",
                "sourceDashboardId": source_dash_id,
                "sourceBlockId": source_block_id,
            },
        ),
        row("demo-schedules", "schedules", 8, {"title": "Schedules"}),
    ]

    data = {
        "items": [
            {
                "id": "r_ship",
                "done": True,
                "name": "Ship dashboard UX audit",
                "owner": "Alex",
                "due": "2026-09-07",
            },
            {
                "id": "r_kanban",
                "done": False,
                "name": "Polish kanban cards",
                "owner": "Sam",
                "due": "2026-09-10",
            },
            {
                "id": "r_tasks",
                "done": False,
                "name": "Wire live agent_tasks",
                "owner": "Alex",
                "due": "2026-09-14",
            },
        ],
        "notes": (
            "## Demo notes\n\n"
            "- Conversation goals live in **chat**, not here.\n"
            "- This board is for **block UX audit** only.\n"
        ),
        "rich_notes": (
            "# Rich markdown\n\n"
            "Use this for **longer** notes with lists:\n\n"
            "1. First step\n2. Second step\n\n"
            "> Quote: boards should skim in under 3 seconds.\n"
        ),
        "photos": [
            {"id": "p1", "url": img_a, "caption": "Demo photo A"},
            {"id": "p2", "url": img_b, "caption": "Demo photo B"},
        ],
        "hero": {
            "url": img_a,
            "caption": "Demo hero caption",
            "headline": "UX Audit Hero",
        },
        "timeline": [
            {
                "id": "t1",
                "date": "2026-09-01",
                "title": "Kickoff",
                "note": "Scoped dashboard blocks",
            },
            {
                "id": "t2",
                "date": "2026-09-05",
                "title": "Harness P3",
                "note": "Plan mode + goal rounds",
            },
            {
                "id": "t3",
                "date": "2026-09-07",
                "title": "UX audit",
                "note": "Screenshot every block",
            },
        ],
        "kpi": {
            "value": "42",
            "label": "Open items",
            "suffix": "",
            "trend": "up",
        },
        "chart": {
            "chartType": "bar",
            "labels": ["Mon", "Tue", "Wed", "Thu", "Fri"],
            "series": [
                {"label": "Done", "data": [3, 5, 2, 6, 4]},
                {"label": "Created", "data": [4, 3, 5, 2, 7]},
            ],
        },
        "spark": {"values": [2, 4, 3, 7, 5, 8, 6, 9, 7]},
        "kanban": {
            "columns": [
                {
                    "id": "col_todo",
                    "title": "Todo",
                    "cards": [
                        {"id": "c1", "title": "Review double chrome"},
                        {"id": "c2", "title": "Increase label font size"},
                    ],
                },
                {
                    "id": "col_doing",
                    "title": "Doing",
                    "cards": [{"id": "c3", "title": "Capture Playwright shots"}],
                },
                {
                    "id": "col_done",
                    "title": "Done",
                    "cards": [{"id": "c4", "title": "Seed demo board"}],
                },
            ]
        },
        "embed": {
            "url": yt_embed,
            "title": "Demo embed (YouTube)",
            "height": 360,
        },
        "media_queue": {
            "now_playing_id": "track-1",
            "items": [
                {
                    "ref": "track-1",
                    "title": "Morning Focus",
                    "artist": "Demo Artist",
                    "source_kind": "embed",
                    "external_url": yt_embed,
                },
                {
                    "ref": "track-2",
                    "title": "Deep Work",
                    "artist": "Demo Artist",
                    "source_kind": "embed",
                    "external_url": yt_embed_2,
                },
            ],
            "shuffle": False,
            "repeat": "off",
        },
        "section_notes": "Nested inside a **section** block — check double chrome here.",
        "cards": [
            {
                "id": "card1",
                "title": "AgentLayer Core",
                "remote_url": "https://example.com/core",
                "tags": ["platform", "runtime"],
                "status": "active",
            },
            {
                "id": "card2",
                "title": "Knowledge Companion",
                "remote_url": "https://example.com/kc",
                "tags": ["rag"],
                "status": "pilot",
            },
            {
                "id": "card3",
                "title": "Media Station",
                "remote_url": "https://example.com/media",
                "tags": ["audio"],
                "status": "active",
            },
        ],
    }
    return {"version": 2, "blocks": blocks}, data


def main() -> int:
    load_e2e_env()
    base = base_url()
    OUT_META.parent.mkdir(parents=True, exist_ok=True)

    with httpx.Client(base_url=base, timeout=120.0) as client:
        email, password = admin_credentials()
        headers, admin_user_id = _login_as(client, email, password)
        friend_user_id = _ensure_friend_for_share(
            client, admin_headers=headers, admin_user_id=admin_user_id
        )
        _ensure_schema(client, headers)
        _delete_by_title(client, headers, TITLE)
        _delete_by_title(client, headers, "UX Audit — Ref Source")

        src_layout = {
            "version": 1,
            "blocks": [
                {
                    "id": "src-md",
                    "type": "markdown",
                    "grid": {"x": 0, "y": 0, "w": 12, "h": 4},
                    "props": {"dataPath": "src_notes", "title": "Source notes"},
                }
            ],
        }
        src = client.post(
            "/v1/dashboards",
            headers=headers,
            json={
                "kind": "custom",
                "title": "UX Audit — Ref Source",
                "ui_layout": src_layout,
                "data": {"src_notes": "Pinned content from source dashboard."},
            },
        )
        src.raise_for_status()
        source_id = str((src.json().get("dashboard") or {}).get("id") or "")
        if not source_id:
            raise RuntimeError("failed to create source dashboard")

        layout, data = build_layout_and_data(
            source_dash_id=source_id,
            source_block_id="src-md",
            friend_user_id=friend_user_id,
        )
        created = client.post(
            "/v1/dashboards",
            headers=headers,
            json={
                "kind": "custom",
                "title": TITLE,
                "ui_layout": layout,
                "data": data,
            },
        )
        created.raise_for_status()
        dash_id = str((created.json().get("dashboard") or {}).get("id") or "")
        if not dash_id:
            raise RuntimeError("failed to create audit dashboard")

        _seed_scheduler_jobs(client, headers, dash_id)

        # Force legacy→collections import + verify
        got = client.get(f"/v1/dashboards/{dash_id}", headers=headers)
        got.raise_for_status()
        projected = (got.json().get("dashboard") or {}).get("data") or {}
        if not (projected.get("items") or projected.get("notes") or projected.get("kpi")):
            raise RuntimeError(
                f"demo data did not project after create: keys={sorted(projected.keys())}"
            )
        timeline = projected.get("timeline") or []
        if not (
            isinstance(timeline, list)
            and timeline
            and isinstance(timeline[0], dict)
            and timeline[0].get("date")
            and timeline[0].get("note")
        ):
            raise RuntimeError(f"timeline demo fields missing: {timeline!r}")
        kpi = projected.get("kpi") or {}
        if not (isinstance(kpi, dict) and kpi.get("trend") == "up"):
            raise RuntimeError(f"kpi trend demo missing: {kpi!r}")

        jobs = client.get(
            "/v1/user/scheduler-jobs",
            headers=headers,
            params={"dashboard_id": dash_id, "limit": 50},
        )
        jobs.raise_for_status()
        job_rows = [
            j
            for j in (jobs.json().get("jobs") or [])
            if isinstance(j, dict) and str(j.get("dashboard_id") or "") == dash_id
        ]
        if not job_rows:
            raise RuntimeError("scheduler demo jobs missing after seed")

        meta = {
            "dashboard_id": dash_id,
            "source_dashboard_id": source_id,
            "friend_user_id": friend_user_id,
            "title": TITLE,
            "url": f"{base}/app/dashboard?id={dash_id}",
            "blocks": [{"id": b["id"], "type": b["type"]} for b in layout["blocks"]],
            "projected_keys": sorted(projected.keys()),
            "scheduler_jobs": len(job_rows),
        }
        OUT_META.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(meta, indent=2))
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
