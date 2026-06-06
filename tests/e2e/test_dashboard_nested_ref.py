"""E2E: nested section block-share, dashboard_ref pin, and block render."""

from __future__ import annotations

import pytest

from tests.e2e.helpers import E2EClient

pytestmark = pytest.mark.e2e

NESTED_LAYOUT = {
    "version": 2,
    "blocks": [
        {
            "id": "sec-e2e",
            "type": "section",
            "grid": {"x": 0, "y": 0, "w": 12, "h": 8},
            "props": {
                "title": "Shared section",
                "collapsed": False,
                "nested": {
                    "version": 2,
                    "blocks": [
                        {
                            "id": "inner-e2e",
                            "type": "markdown",
                            "grid": {"x": 0, "y": 0, "w": 12, "h": 4},
                            "props": {"dataPath": "shared_notes", "placeholder": "Shared"},
                        }
                    ],
                },
            },
        },
        {
            "id": "root-private-e2e",
            "type": "markdown",
            "grid": {"x": 0, "y": 8, "w": 12, "h": 4},
            "props": {"dataPath": "private_notes", "placeholder": "Private"},
        },
    ],
}

SOURCE_LAYOUT = {
    "version": 1,
    "blocks": [
        {
            "id": "src-md-e2e",
            "type": "markdown",
            "grid": {"x": 0, "y": 0, "w": 12, "h": 4},
            "props": {"dataPath": "src_notes", "placeholder": "Source"},
        }
    ],
}


def _ensure_dashboard_schema(client: E2EClient) -> None:
    status = client.get_json("/v1/dashboards/install-status")
    if status.get("schema_installed"):
        return
    offers = status.get("schema_install_offers") or []
    kinds = [o.get("kind") for o in offers if isinstance(o, dict) and o.get("kind")]
    if not kinds:
        kinds = ["custom"]
    client.post_json("/v1/dashboards/install", {"kinds": kinds[:1]})


def _flat_block_ids(ui_layout: dict) -> set[str]:
    ids: set[str] = set()
    for b in ui_layout.get("blocks") or []:
        if not isinstance(b, dict):
            continue
        bid = str(b.get("id") or "").strip()
        if bid:
            ids.add(bid)
        if str(b.get("type") or "").lower() == "section":
            props = b.get("props") if isinstance(b.get("props"), dict) else {}
            nested = props.get("nested") if isinstance(props.get("nested"), dict) else {}
            for nb in nested.get("blocks") or []:
                if isinstance(nb, dict):
                    nid = str(nb.get("id") or "").strip()
                    if nid:
                        ids.add(nid)
    return ids


def test_nested_block_share_and_dashboard_ref_pin(
    admin_client: E2EClient,
    user_b_client: E2EClient,
) -> None:
    _ensure_dashboard_schema(admin_client)
    user_b_id = user_b_client.user_id
    assert user_b_id

    # --- Nested granular block share ---
    shared = admin_client.post_json(
        "/v1/dashboards",
        {
            "kind": "custom",
            "title": "E2E nested share",
            "ui_layout": NESTED_LAYOUT,
            "data": {
                "shared_notes": "visible slice",
                "private_notes": "owner only",
            },
        },
    )
    shared_id = str((shared.get("dashboard") or {}).get("id") or "")
    assert shared_id

    admin_client.post_json(
        f"/v1/dashboards/{shared_id}/block-shares",
        {
            "email": user_b_client.email,
            "block_ids": ["sec-e2e", "inner-e2e"],
            "permission": "view",
        },
    )

    viewer = user_b_client.get_json(f"/v1/dashboards/{shared_id}")
    dash = viewer.get("dashboard") or {}
    assert dash.get("access_scope") == "granular"
    ul = dash.get("ui_layout") or {}
    visible = _flat_block_ids(ul if isinstance(ul, dict) else {})
    assert "inner-e2e" in visible
    assert "root-private-e2e" not in visible
    data = dash.get("data") if isinstance(dash.get("data"), dict) else {}
    assert "shared_notes" in data
    assert "private_notes" not in data

    # --- Pin + dashboard_ref render ---
    source = admin_client.post_json(
        "/v1/dashboards",
        {
            "kind": "custom",
            "title": "E2E ref source",
            "ui_layout": SOURCE_LAYOUT,
            "data": {"src_notes": "hello ref"},
        },
    )
    source_id = str((source.get("dashboard") or {}).get("id") or "")
    assert source_id

    target = admin_client.post_json(
        "/v1/dashboards",
        {"kind": "custom", "title": "E2E ref target", "ui_layout": {"version": 1, "blocks": []}, "data": {}},
    )
    target_id = str((target.get("dashboard") or {}).get("id") or "")
    assert target_id

    pin = admin_client.post_json(
        f"/v1/dashboards/{target_id}/pin-block",
        {
            "source_dashboard_id": source_id,
            "source_block_id": "src-md-e2e",
            "title": "Pinned markdown",
        },
    )
    ref_id = str(pin.get("ref_block_id") or "")
    assert ref_id

    pinned = admin_client.get_json(f"/v1/dashboards/{target_id}")
    pinned_ul = (pinned.get("dashboard") or {}).get("ui_layout") or {}
    pinned_ids = _flat_block_ids(pinned_ul if isinstance(pinned_ul, dict) else {})
    assert ref_id in pinned_ids

    render = admin_client.get_json(f"/v1/dashboards/{source_id}/blocks/src-md-e2e/render")
    assert render.get("ok") is True
    block = render.get("block") or {}
    assert block.get("type") == "markdown"
    assert (render.get("data") or {}).get("src_notes") == "hello ref"

    # User B cannot render source block without full/share access to that block
    denied = user_b_client.http.get(
        f"/v1/dashboards/{source_id}/blocks/src-md-e2e/render",
    )
    assert denied.status_code in (403, 404)
