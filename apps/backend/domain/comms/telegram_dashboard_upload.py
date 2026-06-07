"""Upload images from Telegram into dashboard galleries the user may edit."""

from __future__ import annotations

import uuid
from typing import Any

from apps.backend.core.config import config
from apps.backend.dashboard import db as dashboard_db
from apps.backend.dashboard import file_storage, files_db
from apps.backend.dashboard.upload_bytes import sniff_image_mime
from apps.backend.infrastructure.db import db
from apps.backend.infrastructure.operator_settings import (
    effective_dashboard_upload_max_bytes,
    effective_dashboard_upload_mime,
)


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
    max_b = effective_dashboard_upload_max_bytes()
    allowed = effective_dashboard_upload_mime()
    if len(image_bytes) > max_b:
        raise ValueError(f"image too large (max {max_b} bytes)")
    sniff = sniff_image_mime(image_bytes[:64])
    if sniff is None or sniff not in allowed:
        raise ValueError("unsupported image type")

    access = dashboard_db.dashboard_access_ex(uploader_user_id, tenant_id, dashboard_id)
    if access.role is None:
        raise ValueError("no access to dashboard")
    if access.allowed_block_ids is not None and not access.granular_can_write:
        raise ValueError("read-only share — cannot upload")
    if access.role == "viewer":
        raise ValueError("viewer role — cannot upload")

    from apps.backend.domain.shares.dashboard_grant import dashboard_tenant_id

    row_tid = dashboard_tenant_id(dashboard_id)
    if row_tid is None:
        raise ValueError("dashboard not found")

    fid = uuid.uuid4()
    relpath = f"{row_tid}/{fid}"
    file_storage.write_bytes(config.dashboard_upload_dir(), relpath, image_bytes)
    try:
        row = files_db.file_insert(
            tenant_id=row_tid,
            owner_user_id=uploader_user_id,
            dashboard_id=dashboard_id,
            storage_relpath=relpath,
            content_type=sniff,
            size_bytes=len(image_bytes),
            original_name=original_name[:500],
        )
    except Exception:
        file_storage.unlink_if_exists(config.dashboard_upload_dir(), relpath)
        raise

    gallery_ref = f"wsfile:{row['id']}"
    ws = dashboard_db.dashboard_get(uploader_user_id, tenant_id, dashboard_id)
    if ws is None:
        raise ValueError("could not read dashboard for gallery append")

    data = dict(ws.get("data") or {})
    albums_raw = data.get("albums")
    if not isinstance(albums_raw, list) or not albums_raw:
        raise ValueError("dashboard has no albums — add albums in the UI first")
    if album_index < 0 or album_index >= len(albums_raw):
        raise ValueError("album_index out of range")

    album = dict(albums_raw[album_index]) if isinstance(albums_raw[album_index], dict) else {}
    photos_raw = album.get("photos")
    photos: list[dict[str, Any]] = [dict(x) for x in photos_raw] if isinstance(photos_raw, list) else []
    photos.append(
        {
            "id": f"r_{uuid.uuid4().hex[:12]}",
            "url": gallery_ref,
            "caption": (caption or "")[:500],
        }
    )
    album["photos"] = photos
    albums = list(albums_raw)
    albums[album_index] = album
    data["albums"] = albums

    updated = dashboard_db.dashboard_update(
        uploader_user_id, tenant_id, dashboard_id, data=data
    )
    if updated is None:
        raise ValueError("could not update dashboard gallery")

    return {
        "ok": True,
        "dashboard_id": str(dashboard_id),
        "gallery_ref": gallery_ref,
        "album_index": album_index,
        "photos_count": len(photos),
    }
