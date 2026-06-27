"""Dashboard file upload and public share file endpoints."""
from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response

from apps.backend.api.dashboards.controllers.dashboard_common import require_dashboard_schema, share_password_from_request
from apps.backend.application.dashboards.use_cases.dashboard_controller_services import config
from apps.backend.application.dashboards.use_cases.dashboard_controller_services import db
from apps.backend.application.dashboards.use_cases.dashboard_controller_services import effective_dashboard_upload_max_bytes, effective_dashboard_upload_mime
from apps.backend.application.dashboards.use_cases.dashboard_controller_services import dashboard_db
from apps.backend.application.dashboards.use_cases.dashboard_controller_services import file_storage
from apps.backend.application.dashboards.use_cases.dashboard_controller_services import public_share
from apps.backend.application.dashboards.use_cases.dashboard_controller_services import normalized_content_type, sniff_image_mime
from apps.backend.application.dashboards.use_cases.dashboard_controller_services import col_db
from apps.backend.application.dashboards.use_cases.dashboard_controller_services import attachments_db
from apps.backend.application.identity.use_cases.request_auth import get_current_user
from apps.backend.application.dashboards.use_cases.dashboard_controller_services import http_500_detail

router = APIRouter()

@router.get("/shared/{token}")
async def get_shared_dashboard(token: str, request: Request):
    """Public read-only dashboard view via share token (no auth)."""
    require_dashboard_schema()
    raw = (token or "").strip()
    if len(raw) < 16:
        raise HTTPException(status_code=404, detail="share not found")
    result = public_share.public_share_get_dashboard(
        raw, password=share_password_from_request(request)
    )
    if result.status == "not_found":
        raise HTTPException(status_code=404, detail="share not found or expired")
    if result.status == "password_required":
        return {
            "ok": True,
            "password_required": True,
            "share_label": result.share_label,
        }
    if result.status == "invalid_password":
        raise HTTPException(status_code=401, detail="invalid_password")
    return {"ok": True, "dashboard": result.dashboard}


@router.get("/shared/{token}/files/{file_id}/content")
async def shared_dashboard_file_content(
    token: str, file_id: uuid.UUID, request: Request
):
    """Serve uploaded gallery images referenced in a public share (no auth)."""
    require_dashboard_schema()
    raw = (token or "").strip()
    if len(raw) < 16:
        raise HTTPException(status_code=404, detail="file not found")
    pw = share_password_from_request(request)
    view = public_share.public_share_get_dashboard(raw, password=pw)
    if view.status == "password_required":
        raise HTTPException(status_code=401, detail="password_required")
    if view.status == "invalid_password":
        raise HTTPException(status_code=401, detail="invalid_password")
    if view.status == "not_found":
        raise HTTPException(status_code=404, detail="file not found")
    meta = public_share.public_share_file_access(raw, file_id, password=pw)
    if not meta:
        raise HTTPException(status_code=404, detail="file not found")
    try:
        data = file_storage.read_bytes(config.dashboard_upload_dir(), meta["storage_relpath"])
    except (OSError, ValueError):
        raise HTTPException(status_code=404, detail="file not found") from None
    return Response(
        content=data,
        media_type=meta.get("content_type") or "application/octet-stream",
    )


@router.get("/files/{file_id}/content")
async def dashboard_file_content(request: Request, file_id: uuid.UUID):
    require_dashboard_schema()
    user = await get_current_user(request)
    tid = db.user_tenant_id(user.id)
    meta = attachments_db.attachment_get_with_access(file_id, user.id, tid)
    if not meta:
        raise HTTPException(status_code=404, detail="file not found")
    try:
        data = file_storage.read_bytes(config.dashboard_upload_dir(), meta["storage_relpath"])
    except (OSError, ValueError):
        raise HTTPException(status_code=404, detail="file not found") from None
    return Response(
        content=data,
        media_type=meta.get("content_type") or "application/octet-stream",
    )


@router.delete("/files/{file_id}")
async def dashboard_file_delete(request: Request, file_id: uuid.UUID):
    require_dashboard_schema()
    user = await get_current_user(request)
    tid = db.user_tenant_id(user.id)
    rel = attachments_db.attachment_delete_with_access(file_id, user.id, tid)
    if rel is None:
        raise HTTPException(status_code=404, detail="file not found")
    file_storage.unlink_if_exists(config.dashboard_upload_dir(), rel)
    return {"ok": True, "deleted": True}


@router.post("/{dashboard_id}/files")
async def dashboard_file_upload(
    request: Request,
    dashboard_id: uuid.UUID,
    file: UploadFile = File(...),
    append_list_path: str | None = Form(default=None),
    caption: str = Form(default=""),
):
    require_dashboard_schema()
    user = await get_current_user(request)
    tid = db.user_tenant_id(user.id)
    ws = dashboard_db.dashboard_get(user.id, tid, dashboard_id)
    if not ws:
        raise HTTPException(status_code=404, detail="dashboard not found")
    role = ws.get("access_role")
    if role not in ("owner", "co_owner", "editor"):
        raise HTTPException(status_code=403, detail="upload not allowed for this role")

    max_b = effective_dashboard_upload_max_bytes()
    allowed = effective_dashboard_upload_mime()
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

    sniff = sniff_image_mime(data[:64])
    declared = normalized_content_type(file.content_type)
    if sniff is None or sniff not in allowed:
        raise HTTPException(
            status_code=415,
            detail="unsupported or invalid image type",
        )
    if declared and declared not in allowed:
        raise HTTPException(status_code=415, detail="content type not allowed")
    if declared and declared != sniff:
        raise HTTPException(
            status_code=400,
            detail=f"content type mismatch (declared {declared}, actual {sniff})",
        )

    fid = uuid.uuid4()
    relpath = f"{tid}/{fid}"
    name = (file.filename or "").strip()[:500]
    try:
        file_storage.write_bytes(config.dashboard_upload_dir(), relpath, data)
    except OSError as e:
        raise HTTPException(status_code=500, detail=http_500_detail(e)) from e

    from apps.backend.application.dashboards.use_cases.dashboard_controller_services import collections_view_service as domain_svc

    bindings = domain_svc.resolve_bindings_for_dashboard(ws)
    default_slug = next(iter(bindings.values()), None) if bindings else None
    collection_id = None
    if default_slug:
        col = col_db.collection_get(user.id, default_slug)
        if col:
            collection_id = uuid.UUID(str(col["id"]))

    try:
        row = col_db.attachment_insert(
            tenant_id=tid,
            owner_user_id=user.id,
            storage_relpath=relpath,
            content_type=sniff,
            size_bytes=len(data),
            original_name=name,
            collection_id=collection_id,
            dashboard_id=dashboard_id,
        )
    except Exception:
        file_storage.unlink_if_exists(config.dashboard_upload_dir(), relpath)
        raise

    gallery_ref = str(row.get("gallery_ref") or f"file:{row['id']}")
    out: dict[str, Any] = {
        "ok": True,
        "file": {
            "id": row["id"],
            "dashboard_id": str(dashboard_id),
            "content_type": row["content_type"],
            "size_bytes": row["size_bytes"],
            "gallery_ref": gallery_ref,
        },
    }
    lp = (append_list_path or "").strip()
    if lp:
        from apps.backend.application.dashboards.use_cases.dashboard_controller_services import append_list_rows

        append = append_list_rows(
            user.id,
            tid,
            dashboard_id,
            list_path=lp,
            rows=[{"url": gallery_ref, "caption": (caption or "")[:500]}],
        )
        if not append.get("ok"):
            out["gallery_append_error"] = str(append.get("error") or "list_append failed")
        else:
            out["appended_to"] = lp
            out["append"] = append
    return out
