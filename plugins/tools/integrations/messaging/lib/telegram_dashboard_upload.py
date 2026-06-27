"""Upload images from Telegram into dashboard galleries the user may edit."""

from __future__ import annotations

import uuid
from typing import Any

from apps.backend.infrastructure.dashboards import dashboard_db
from apps.backend.infrastructure.dashboards.dashboard_file_upload import store_dashboard_image
from apps.backend.infrastructure.db import db


def _default_album_index(data: dict[str, Any]) -> int:
    albums = data.get("albums")
    return 0 if isinstance(albums, list) and albums else 0


def list_telegram_upload_targets(grantee_user_id: uuid.UUID) -> list[dict[str, Any]]:
    """Dashboards with gallery albums the user may edit (member, block grant, or friend share)."""
    tid = db.user_tenant_id(grantee_user_id)
    rows = dashboard_db.dashboard_list(grantee_user_id, tid, limit=100)
    targets: list[dict[str, Any]] = []

    for row in rows:
        did_raw = row.get("id")
        if not did_raw:
            continue
        try:
            did = uuid.UUID(str(did_raw))
        except ValueError:
            continue

        access = dashboard_db.dashboard_access_ex(grantee_user_id, tid, did)
        if access.role is None:
            continue
        can_upload = access.role in ("owner", "co_owner", "editor") or access.granular_can_write
        if not can_upload:
            continue

        ws = dashboard_db.dashboard_get(grantee_user_id, tid, did)
        if ws is None:
            continue
        data = ws.get("data") if isinstance(ws.get("data"), dict) else {}
        albums = data.get("albums")
        if not isinstance(albums, list) or not albums:
            continue

        targets.append(
            {
                "dashboard_id": str(did),
                "title": str(ws.get("title") or row.get("title") or ""),
                "kind": str(ws.get("kind") or row.get("kind") or ""),
                "album_index": _default_album_index(data),
            }
        )
    return targets


def upload_image_bytes(
    *,
    uploader_user_id: uuid.UUID,
    tenant_id: int,
    dashboard_id: uuid.UUID,
    image_bytes: bytes,
    original_name: str = "telegram.jpg",
    album_index: int = 0,
    caption: str = "",
) -> dict[str, Any]:
    """Store file and append gallery entry when uploader has edit access."""
    stored = store_dashboard_image(
        uploader_user_id,
        tenant_id,
        dashboard_id,
        image_bytes,
        original_name=original_name,
    )
    if not stored.get("ok"):
        raise ValueError(str(stored.get("error") or "upload failed"))

    gallery_ref = str(stored.get("gallery_ref") or "")
    from apps.backend.infrastructure.dashboards.dashboard_list_ops import append_list_rows

    list_path = f"albums.{album_index}.photos"
    result = append_list_rows(
        uploader_user_id,
        tenant_id,
        dashboard_id,
        list_path=list_path,
        rows=[{"url": gallery_ref, "caption": (caption or "")[:500]}],
    )
    if not result.get("ok"):
        raise ValueError(str(result.get("error") or "gallery append failed"))

    return {
        "ok": True,
        "dashboard_id": str(dashboard_id),
        "gallery_ref": gallery_ref,
        "album_index": album_index,
        "photos_count": int(result.get("total_count") or 0),
        "source": "domain",
    }
