"""HTTP API for user media library (``/v1/media``)."""

from __future__ import annotations

import re
import uuid
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

from apps.backend.core.config import config
from apps.backend.dashboard import file_storage
from apps.backend.dashboard import db as dashboard_db
from apps.backend.dashboard.upload_bytes import normalized_content_type
from apps.backend.infrastructure.auth import get_current_user, get_user_by_email
from apps.backend.infrastructure.db import db
from apps.backend.infrastructure.public_error import http_500_detail
from apps.backend.media import media_db, media_policy
from apps.backend.media.upload_bytes import sniff_media_mime

router = APIRouter(prefix="/v1/media", tags=["media"])

_RANGE_RE = re.compile(r"^bytes=(\d+)-(\d*)$", re.IGNORECASE)


def _require_schema() -> None:
    if not media_db.media_tables_exist():
        raise HTTPException(
            status_code=400,
            detail="media schema not installed; run database migrations (schema_080)",
        )


def _require_library(user_id: uuid.UUID) -> None:
    if not media_policy.effective_media_library_enabled(user_id=user_id):
        raise HTTPException(status_code=403, detail="media library disabled")


def _require_upload(user_id: uuid.UUID) -> None:
    _require_library(user_id)
    if not media_policy.effective_media_upload_enabled(user_id=user_id):
        raise HTTPException(status_code=403, detail="media upload disabled")


def _optional_dashboard(
    user_id: uuid.UUID, tenant_id: int, dashboard_id: uuid.UUID | None
) -> None:
    if dashboard_id is None:
        return
    ws = dashboard_db.dashboard_get(user_id, tenant_id, dashboard_id)
    if not ws:
        raise HTTPException(status_code=404, detail="dashboard not found")
    role = ws.get("access_role")
    if role not in ("owner", "co_owner", "editor"):
        raise HTTPException(status_code=403, detail="dashboard access denied")


def _public_item(row: dict[str, Any]) -> dict[str, Any]:
    out = {
        "id": row["id"],
        "source_kind": row["source_kind"],
        "title": row["title"],
        "artist": row["artist"],
        "album": row["album"],
        "duration_sec": row.get("duration_sec"),
        "cover_url": row.get("cover_url") or "",
        "external_url": row.get("external_url") or "",
        "embed_provider": row.get("embed_provider") or "",
        "content_type": row.get("content_type") or "",
        "size_bytes": row.get("size_bytes") or 0,
        "original_name": row.get("original_name") or "",
        "dashboard_id": row.get("dashboard_id"),
        "license": row.get("license"),
        "license_note": row.get("license_note") or "",
        "tags": row.get("tags") or [],
        "created_at": row.get("created_at") or "",
        "media_ref": f"media:{row['id']}",
        "shareable": media_policy.item_is_shareable(row),
    }
    if row.get("access"):
        out["access"] = row["access"]
    if row.get("share_permission"):
        out["share_permission"] = row["share_permission"]
    if row.get("source_kind") == "upload":
        out["stream_url"] = f"/v1/media/items/{row['id']}/stream"
    return out


def _stream_bytes(data: bytes, request: Request, content_type: str) -> Response:
    total = len(data)
    range_hdr = (request.headers.get("range") or "").strip()
    if range_hdr:
        m = _RANGE_RE.match(range_hdr)
        if m:
            start = int(m.group(1))
            end = int(m.group(2)) if m.group(2) else total - 1
            end = min(end, total - 1)
            if 0 <= start <= end < total:
                chunk = data[start : end + 1]
                return Response(
                    content=chunk,
                    status_code=206,
                    media_type=content_type,
                    headers={
                        "Accept-Ranges": "bytes",
                        "Content-Range": f"bytes {start}-{end}/{total}",
                        "Content-Length": str(len(chunk)),
                    },
                )
    return Response(
        content=data,
        media_type=content_type,
        headers={
            "Accept-Ranges": "bytes",
            "Content-Length": str(total),
        },
    )


class MediaEmbedBody(BaseModel):
    external_url: str = Field(..., min_length=8, max_length=2048)
    title: str = Field(default="", max_length=500)
    artist: str = Field(default="", max_length=500)
    dashboard_id: str | None = Field(default=None, max_length=36)


class MediaLicensePatchBody(BaseModel):
    license: str = Field(..., min_length=3, max_length=32)
    license_note: str = Field(default="", max_length=2000)


class MediaShareBody(BaseModel):
    email: str = Field(..., min_length=3, max_length=254)
    permission: str = Field(default="play", max_length=32)


@router.get("/limits")
async def media_limits(request: Request):
    user = await get_current_user(request)
    _require_schema()
    return {
        "ok": True,
        "library_enabled": media_policy.effective_media_library_enabled(user_id=user.id),
        "upload_enabled": media_policy.effective_media_upload_enabled(user_id=user.id),
        "sharing_enabled": media_policy.effective_media_sharing_enabled(user_id=user.id),
        "max_file_bytes": media_policy.effective_media_upload_max_bytes(),
        "allowed_mime": sorted(media_policy.effective_media_upload_mime()),
        "embed_hosts": sorted(media_policy.effective_media_embed_hosts()),
        "stream_hosts": sorted(media_policy.effective_media_stream_hosts()),
    }


@router.get("/quota")
async def media_quota(request: Request):
    user = await get_current_user(request)
    _require_schema()
    tid = db.user_tenant_id(user.id)
    snap = media_policy.media_quota_snapshot(user_id=user.id, tenant_id=tid)
    return {"ok": True, **snap}


@router.get("/items")
async def media_list_items(request: Request, source_kind: str | None = None):
    user = await get_current_user(request)
    _require_schema()
    _require_library(user.id)
    tid = db.user_tenant_id(user.id)
    sk = (source_kind or "").strip() or None
    if sk and sk not in ("embed", "upload", "external_link", "archive"):
        raise HTTPException(status_code=400, detail="invalid source_kind")
    rows = media_db.item_list_accessible(user_id=user.id, tenant_id=tid, source_kind=sk)
    return {"ok": True, "items": [_public_item(r) for r in rows]}


@router.post("/items/upload")
async def media_upload_item(
    request: Request,
    file: UploadFile = File(...),
    title: str = Form(default=""),
    artist: str = Form(default=""),
    dashboard_id: str | None = Form(default=None),
):
    _require_schema()
    user = await get_current_user(request)
    _require_upload(user.id)
    tid = db.user_tenant_id(user.id)

    dash_uuid: uuid.UUID | None = None
    if dashboard_id and dashboard_id.strip():
        try:
            dash_uuid = uuid.UUID(dashboard_id.strip())
        except ValueError as e:
            raise HTTPException(status_code=400, detail="invalid dashboard_id") from e
        _optional_dashboard(user.id, tid, dash_uuid)

    max_b = media_policy.effective_media_upload_max_bytes()
    allowed = media_policy.effective_media_upload_mime()
    chunks: list[bytes] = []
    total = 0
    while True:
        block = await file.read(1024 * 64)
        if not block:
            break
        total += len(block)
        if total > max_b:
            raise HTTPException(
                status_code=413,
                detail=f"file too large (max {max_b} bytes)",
            )
        chunks.append(block)
    data = b"".join(chunks)
    if not data:
        raise HTTPException(status_code=400, detail="empty file")

    sniff = sniff_media_mime(data[:64])
    declared = normalized_content_type(file.content_type)
    if sniff is None or sniff not in allowed:
        raise HTTPException(status_code=415, detail="unsupported or invalid media type")
    if declared and declared not in allowed:
        raise HTTPException(status_code=415, detail="content type not allowed")
    if declared and declared != sniff:
        raise HTTPException(
            status_code=400,
            detail=f"content type mismatch (declared {declared}, actual {sniff})",
        )

    used = media_db.user_upload_bytes_used(user_id=user.id, tenant_id=tid)
    quota = media_policy.effective_media_quota_bytes(user_id=user.id)
    if used + len(data) > quota:
        raise HTTPException(
            status_code=413,
            detail=f"storage quota exceeded ({used + len(data)} > {quota} bytes)",
        )

    fid = uuid.uuid4()
    relpath = f"{tid}/{fid}"
    name = (file.filename or "").strip()[:500]
    try:
        file_storage.write_bytes(config.media_upload_dir(), relpath, data)
    except OSError as e:
        raise HTTPException(status_code=500, detail=http_500_detail(e)) from e

    try:
        row = media_db.item_insert_upload(
            tenant_id=tid,
            owner_user_id=user.id,
            dashboard_id=dash_uuid,
            storage_relpath=relpath,
            content_type=sniff,
            size_bytes=len(data),
            original_name=name,
            title=(title or name).strip()[:500],
            artist=artist.strip()[:500],
        )
    except Exception:
        file_storage.unlink_if_exists(config.media_upload_dir(), relpath)
        raise

    return {"ok": True, "item": _public_item(row)}


@router.post("/items/embed")
async def media_add_embed(request: Request, body: MediaEmbedBody):
    _require_schema()
    user = await get_current_user(request)
    _require_library(user.id)
    tid = db.user_tenant_id(user.id)

    url = body.external_url.strip()
    if not media_policy.embed_url_allowed(url):
        raise HTTPException(status_code=400, detail="embed URL not allowed")

    dash_uuid: uuid.UUID | None = None
    if body.dashboard_id and body.dashboard_id.strip():
        try:
            dash_uuid = uuid.UUID(body.dashboard_id.strip())
        except ValueError as e:
            raise HTTPException(status_code=400, detail="invalid dashboard_id") from e
        _optional_dashboard(user.id, tid, dash_uuid)

    row = media_db.item_insert_embed(
        tenant_id=tid,
        owner_user_id=user.id,
        dashboard_id=dash_uuid,
        external_url=url,
        embed_provider=media_policy.embed_provider_for_url(url),
        title=body.title.strip(),
        artist=body.artist.strip(),
    )
    return {"ok": True, "item": _public_item(row)}


@router.get("/items/{item_id}")
async def media_get_item(request: Request, item_id: uuid.UUID):
    _require_schema()
    user = await get_current_user(request)
    _require_library(user.id)
    tid = db.user_tenant_id(user.id)
    row, share_perm, is_owner = media_db.item_get_with_access(item_id, user.id, tid)
    if not row:
        raise HTTPException(status_code=404, detail="media item not found")
    if is_owner:
        row["access"] = "owner"
    else:
        row["access"] = "shared"
        row["share_permission"] = share_perm
    return {"ok": True, "item": _public_item(row)}


@router.patch("/items/{item_id}")
async def media_patch_item(request: Request, item_id: uuid.UUID, body: MediaLicensePatchBody):
    _require_schema()
    user = await get_current_user(request)
    _require_library(user.id)
    tid = db.user_tenant_id(user.id)
    lic = media_policy.normalize_media_license(body.license)
    if not lic:
        raise HTTPException(status_code=400, detail="invalid license")
    row = media_db.item_update_license(
        item_id=item_id,
        owner_user_id=user.id,
        tenant_id=tid,
        license=lic,
        license_note=body.license_note.strip(),
    )
    if not row:
        raise HTTPException(status_code=404, detail="upload item not found")
    row["access"] = "owner"
    return {"ok": True, "item": _public_item(row)}


@router.get("/items/{item_id}/stream")
async def media_stream_item(request: Request, item_id: uuid.UUID):
    _require_schema()
    user = await get_current_user(request)
    _require_library(user.id)
    tid = db.user_tenant_id(user.id)
    row, share_perm, is_owner = media_db.item_get_with_access(item_id, user.id, tid)
    if not row or row.get("source_kind") != "upload":
        raise HTTPException(status_code=404, detail="media stream not found")
    relpath = row.get("storage_relpath") or ""
    if not relpath:
        raise HTTPException(status_code=404, detail="media stream not found")
    try:
        data = file_storage.read_bytes(config.media_upload_dir(), relpath)
    except OSError as e:
        raise HTTPException(status_code=404, detail="media file missing on disk") from e
    headers_extra: dict[str, str] = {}
    if not is_owner and share_perm == "play_and_download":
        name = (row.get("original_name") or row.get("title") or "media").strip()[:200]
        headers_extra["Content-Disposition"] = f'attachment; filename="{name}"'
    resp = _stream_bytes(data, request, row.get("content_type") or "application/octet-stream")
    for k, v in headers_extra.items():
        resp.headers[k] = v
    return resp


@router.delete("/items/{item_id}")
async def media_delete_item(request: Request, item_id: uuid.UUID):
    _require_schema()
    user = await get_current_user(request)
    _require_library(user.id)
    tid = db.user_tenant_id(user.id)
    relpath = media_db.item_soft_delete(item_id, user.id, tid)
    if relpath is None:
        raise HTTPException(status_code=404, detail="media item not found")
    if relpath:
        file_storage.unlink_if_exists(config.media_upload_dir(), relpath)
    return {"ok": True, "deleted": True}


@router.get("/items/{item_id}/shares")
async def media_list_item_shares(request: Request, item_id: uuid.UUID):
    _require_schema()
    user = await get_current_user(request)
    _require_library(user.id)
    tid = db.user_tenant_id(user.id)
    if not media_db.item_get_owned(item_id, user.id, tid):
        raise HTTPException(status_code=404, detail="media item not found")
    grants = media_db.share_grants_list(
        owner_user_id=user.id, tenant_id=tid, media_item_id=item_id
    )
    return {"ok": True, "grants": grants}


@router.post("/items/{item_id}/share")
async def media_share_item(request: Request, item_id: uuid.UUID, body: MediaShareBody):
    _require_schema()
    user = await get_current_user(request)
    _require_library(user.id)
    if not media_policy.effective_media_sharing_enabled(user_id=user.id):
        raise HTTPException(status_code=403, detail="media sharing disabled")
    if not media_db.media_share_tables_exist():
        raise HTTPException(status_code=400, detail="media sharing schema not installed")
    tid = db.user_tenant_id(user.id)
    target = get_user_by_email(body.email.strip().lower())
    if target is None:
        raise HTTPException(status_code=404, detail="user not found for this email")
    perm = (body.permission or "play").strip().lower()
    if perm not in ("play", "play_and_download"):
        raise HTTPException(status_code=400, detail="permission must be play or play_and_download")
    grant = media_db.share_grant_upsert(
        owner_user_id=user.id,
        tenant_id=tid,
        media_item_id=item_id,
        viewer_user_id=target.id,
        permission=perm,
    )
    if not grant:
        raise HTTPException(
            status_code=400,
            detail="could not share (upload only, license required, same tenant, not self)",
        )
    return {"ok": True, "grant": grant}


@router.delete("/share-grants/{grant_id}")
async def media_revoke_share(request: Request, grant_id: uuid.UUID):
    _require_schema()
    user = await get_current_user(request)
    _require_library(user.id)
    tid = db.user_tenant_id(user.id)
    if not media_db.share_grant_delete(owner_user_id=user.id, tenant_id=tid, grant_id=grant_id):
        raise HTTPException(status_code=404, detail="share grant not found")
    return {"ok": True, "removed": True}
