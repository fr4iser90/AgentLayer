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
from apps.backend.application.dashboards.use_cases.dashboard_controller_services import (
    decode_text_payload,
    is_image_mime,
    is_text_like_mime,
    normalized_content_type,
    sniff_upload_mime,
)
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


def _apply_text_to_data_path(
    *,
    user_id: uuid.UUID,
    tenant_id: int,
    dashboard_id: uuid.UUID,
    ws: dict[str, Any],
    text_path: str,
    text: str,
) -> dict[str, Any]:
    """Write extracted text into a bound collection field (markdown strategy a)."""
    from apps.backend.application.dashboards.use_cases.dashboard_controller_services import collections_view_service as domain_svc
    from apps.backend.application.dashboards.use_cases.dashboard_controller_services import top_level_key

    path = (text_path or "").strip()
    if not path:
        return {"ok": False, "error": "empty text path"}

    owner_raw = ws.get("owner_user_id")
    try:
        owner_uid = uuid.UUID(str(owner_raw)) if owner_raw else user_id
    except (ValueError, TypeError):
        owner_uid = user_id
    row_tid = int(ws.get("tenant_id") or tenant_id)

    if ws.get("access_scope") == "granular":
        from apps.backend.application.dashboards.use_cases.dashboard_controller_services import (
            data_paths_from_blocks,
        )

        ul = ws.get("ui_layout") if isinstance(ws.get("ui_layout"), dict) else {}
        blocks = ul.get("blocks") if isinstance(ul.get("blocks"), list) else []
        allowed = {top_level_key(dp) for dp in data_paths_from_blocks(blocks) if dp}
        if top_level_key(path) not in allowed:
            return {"ok": False, "error": f"granular share cannot write data.{top_level_key(path)!r}"}

    bindings = domain_svc.resolve_bindings_for_dashboard(ws)
    result = domain_svc.patch_fields(
        owner_user_id=owner_uid,
        tenant_id=row_tid,
        bindings=bindings,
        ui_layout=ws.get("ui_layout") if isinstance(ws.get("ui_layout"), dict) else None,
        patches=[{"path": path, "value": text}],
    )
    if not result.get("ok"):
        return {"ok": False, "error": str(result.get("error") or "text patch failed")}
    return {"ok": True, "path": path, "patch": result}


@router.get("/{dashboard_id}/files")
async def dashboard_files_list(request: Request, dashboard_id: uuid.UUID):
    """List board attachments (Board-Dateien) for a dashboard."""
    require_dashboard_schema()
    user = await get_current_user(request)
    tid = db.user_tenant_id(user.id)
    ws = dashboard_db.dashboard_get(user.id, tid, dashboard_id)
    if not ws:
        raise HTTPException(status_code=404, detail="dashboard not found")
    row_tid = int(ws.get("tenant_id") or tid)
    files = attachments_db.attachment_list_for_dashboard(dashboard_id, row_tid, limit=200)
    return {"ok": True, "files": files}


@router.post("/{dashboard_id}/files")
async def dashboard_file_upload(
    request: Request,
    dashboard_id: uuid.UUID,
    file: UploadFile = File(...),
    append_list_path: str | None = Form(default=None),
    append_text_path: str | None = Form(default=None),
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

    name = (file.filename or "").strip()[:500]
    declared = normalized_content_type(file.content_type)
    sniff = sniff_upload_mime(data, filename=name, declared=declared)
    if sniff is None or sniff not in allowed:
        raise HTTPException(
            status_code=415,
            detail="unsupported or invalid file type",
        )
    if declared and declared not in allowed:
        # Allow browsers that send application/octet-stream for .md when sniff succeeded
        if declared not in ("application/octet-stream", "binary/octet-stream"):
            raise HTTPException(status_code=415, detail="content type not allowed")
    if declared and declared in allowed and declared != sniff and is_image_mime(sniff):
        raise HTTPException(
            status_code=400,
            detail=f"content type mismatch (declared {declared}, actual {sniff})",
        )

    fid = uuid.uuid4()
    relpath = f"{tid}/{fid}"
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
            "original_name": name,
            "gallery_ref": gallery_ref,
            "file_ref": gallery_ref,
        },
    }
    lp = (append_list_path or "").strip()
    if lp:
        if not is_image_mime(sniff):
            out["gallery_append_error"] = "append_list_path requires an image upload"
        else:
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

    tp = (append_text_path or "").strip()
    if tp:
        if not is_text_like_mime(sniff):
            out["text_apply_error"] = "append_text_path requires a text/markdown upload"
        else:
            text = decode_text_payload(data)
            if text is None:
                out["text_apply_error"] = "file is not valid UTF-8 text"
            else:
                applied = _apply_text_to_data_path(
                    user_id=user.id,
                    tenant_id=tid,
                    dashboard_id=dashboard_id,
                    ws=ws,
                    text_path=tp,
                    text=text,
                )
                if not applied.get("ok"):
                    out["text_apply_error"] = str(applied.get("error") or "text apply failed")
                else:
                    out["text_applied_to"] = tp
                    out["text_chars"] = len(text)
                    out["source_file_ref"] = gallery_ref
    return out
