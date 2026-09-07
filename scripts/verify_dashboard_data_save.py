#!/usr/bin/env python3
"""Verify that ``PATCH /v1/dashboards/{id}`` persists board content.

Round-trips a table row edit, a markdown string, a nested timeline field, a row
deletion, an emptied list and ``_agentlayer`` config against the seeded UX-audit
board. The original rows are restored at the end so the script can be re-run.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from tests.e2e.support.helpers import (  # noqa: E402
    admin_credentials,
    base_url,
    load_e2e_env,
)

META = REPO / "example" / "dashboard-ux-audit" / "dashboard.json"


def _login(client: httpx.Client) -> dict:
    email, password = admin_credentials()
    r = client.post("/auth/login", json={"email": email, "password": password})
    r.raise_for_status()
    token = r.json().get("access_token")
    if not token:
        raise RuntimeError("login missing access_token")
    return {"Authorization": f"Bearer {token}"}


def _get_data(client: httpx.Client, headers: dict, dash_id: str) -> dict:
    r = client.get(f"/v1/dashboards/{dash_id}", headers=headers)
    r.raise_for_status()
    return (r.json().get("dashboard") or {}).get("data") or {}


def _patch(client: httpx.Client, headers: dict, dash_id: str, data: dict) -> dict:
    r = client.patch(f"/v1/dashboards/{dash_id}", headers=headers, json={"data": data})
    r.raise_for_status()
    return (r.json().get("dashboard") or {}).get("data") or {}


def main() -> int:
    load_e2e_env()
    if not META.is_file():
        raise SystemExit(f"missing {META} — run scripts/seed_dashboard_ux_audit.py first")
    dash_id = json.loads(META.read_text(encoding="utf-8"))["dashboard_id"]

    failures: list[str] = []
    with httpx.Client(base_url=base_url(), timeout=60.0) as client:
        headers = _login(client)
        before = _get_data(client, headers, dash_id)

        items = [dict(r) for r in (before.get("items") or []) if isinstance(r, dict)]
        timeline = [dict(r) for r in (before.get("timeline") or []) if isinstance(r, dict)]
        if not items or not timeline:
            raise SystemExit(f"board has no demo content: keys={sorted(before.keys())}")

        original_items = [dict(r) for r in items]
        original_notes = before.get("notes")
        original_timeline = [dict(r) for r in timeline]

        # Add a row we own, so the later deletion check does not eat seeded content.
        temp_row = {**items[0], "id": "r_roundtrip_temp", "name": "SAVE-ROUNDTRIP-TEMP"}
        edited_items = [{**items[0], "name": "SAVE-ROUNDTRIP-OK"}, *items[1:], temp_row]
        timeline[0]["note"] = "note edited via PATCH"

        payload = {
            "items": edited_items,
            "notes": "# Save works\n\nEdited via PATCH.",
            "timeline": timeline,
            "_agentlayer": {"system_prompt_extra": "roundtrip marker"},
        }
        echoed = _patch(client, headers, dash_id, payload)
        reread = _get_data(client, headers, dash_id)

        for label, got in (("patch response", echoed), ("fresh GET", reread)):
            rows = [r for r in (got.get("items") or []) if isinstance(r, dict)]
            names = [str(r.get("name") or "") for r in rows]
            if "SAVE-ROUNDTRIP-OK" not in names:
                failures.append(f"{label}: edited table row missing (names={names})")
            if "SAVE-ROUNDTRIP-TEMP" not in names:
                failures.append(f"{label}: appended table row missing (names={names})")
            if not str(got.get("notes") or "").startswith("# Save works"):
                failures.append(f"{label}: markdown not persisted ({got.get('notes')!r})")
            tl = [r for r in (got.get("timeline") or []) if isinstance(r, dict)]
            first_note = str(tl[0].get("note") or "") if tl else ""
            if first_note != "note edited via PATCH":
                failures.append(f"{label}: timeline note not persisted ({first_note!r})")
            first_date = str(tl[0].get("date") or "") if tl else ""
            if not first_date:
                failures.append(f"{label}: timeline date lost")
            al = got.get("_agentlayer")
            if not isinstance(al, dict) or al.get("system_prompt_extra") != "roundtrip marker":
                failures.append(f"{label}: _agentlayer config not persisted ({al!r})")

        # Deleting the row we appended must stick.
        kept_items = [r for r in edited_items if str(r.get("id")) != "r_roundtrip_temp"]
        _patch(client, headers, dash_id, {"items": kept_items})
        after_delete = _get_data(client, headers, dash_id)
        if any(
            str((r or {}).get("id")) == "r_roundtrip_temp"
            for r in (after_delete.get("items") or [])
        ):
            failures.append("deleted row r_roundtrip_temp came back")

        # Partial save must not wipe lists the client did not send.
        _patch(client, headers, dash_id, {"notes": "# Partial save"})
        after_partial = _get_data(client, headers, dash_id)
        if len(after_partial.get("items") or []) != len(kept_items):
            failures.append(
                "partial save wiped items "
                f"({len(after_partial.get('items') or [])} != {len(kept_items)})"
            )
        if not (after_partial.get("photos") or []):
            failures.append("partial save wiped photos")

        # Clearing a list must stay cleared — it must not be refilled from legacy data.
        _patch(client, headers, dash_id, {"items": []})
        after_clear = _get_data(client, headers, dash_id)
        if after_clear.get("items"):
            failures.append(
                f"cleared list resurrected {len(after_clear['items'])} legacy rows"
            )

        # Restore the board so this script is re-runnable.
        _patch(
            client,
            headers,
            dash_id,
            {"items": original_items, "notes": original_notes, "timeline": original_timeline},
        )
        restored = _get_data(client, headers, dash_id)
        if len(restored.get("items") or []) != len(original_items):
            failures.append(
                "restore failed "
                f"({len(restored.get('items') or [])} != {len(original_items)})"
            )

    if failures:
        print("FAILED:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("OK — dashboard data round-trips through PATCH (edit, add, delete, clear, partial, config)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
