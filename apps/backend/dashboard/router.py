"""HTTP API for generic dashboards (``/v1/dashboards``)."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

from apps.backend.core.config import config
from apps.backend.infrastructure.auth import get_current_user, get_user_by_email
from apps.backend.infrastructure.db import db
from apps.backend.infrastructure.operator_settings import (
    effective_dashboard_upload_max_bytes,
    effective_dashboard_upload_mime,
)
from apps.backend.dashboard import db as dashboard_db
from apps.backend.dashboard import file_storage, files_db, public_share
from apps.backend.dashboard.block_ref import render_block_from_dashboard
from apps.backend.dashboard.bootstrap import ensure_dashboard_schema, dashboard_tables_exist
from apps.backend.dashboard.pins import pin_block_to_dashboard
from apps.backend.dashboard.template_ops import export_template_payload, validate_template_import
from apps.backend.dashboard.layout_proposals import (
    apply_layout_proposal,
    get_latest_proposal_set,
    get_proposal_set,
)
from apps.backend.dashboard.setup import attach_onboarding, onboarding_for_kind
from apps.backend.dashboard.upload_bytes import normalized_content_type, sniff_image_mime
from apps.backend.infrastructure.public_error import http_500_detail

router = APIRouter(prefix="/v1/dashboards", tags=["dashboards"])


def _require_schema() -> None:
    if not dashboard_tables_exist():
        raise HTTPException(
            status_code=400,
            detail="dashboard schema not installed; use POST /v1/dashboards/install from the UI first",
        )


class DashboardCreateBody(BaseModel):
    kind: str = Field(default="custom", max_length=64)
    template_id: str | None = Field(default=None, max_length=64)
    title: str = Field(default="", max_length=500)
    ui_layout: dict[str, Any] | None = None
    data: dict[str, Any] | None = None


class DashboardPatchBody(BaseModel):
    title: str | None = Field(default=None, max_length=500)
    ui_layout: dict[str, Any] | None = None
    data: dict[str, Any] | None = None


class DashboardMemberAddBody(BaseModel):
    email: str = Field(..., min_length=3, max_length=254)
    role: str = Field(default="viewer", max_length=16)


class DashboardBlockShareBody(BaseModel):
    """Share only specific layout block ids; ``view`` = read-only, ``edit`` = patch those blocks."""

    email: str = Field(..., min_length=3, max_length=254)
    block_ids: list[str] = Field(default_factory=list)
    permission: str = Field(default="view", max_length=8)


class DashboardPublicShareCreateBody(BaseModel):
    """Create a public read-only link. Empty ``block_ids`` = entire dashboard."""

    block_ids: list[str] = Field(default_factory=list)
    label: str = Field(default="", max_length=200)
    expires_at: str | None = Field(
        default=None,
        description="Optional ISO-8601 expiry (UTC). Omit for no expiry.",
    )
    password: str | None = Field(
        default=None,
        max_length=128,
        description="Optional link password (min 4 chars). Omit for open links.",
    )


def _share_password_from_request(request: Request) -> str | None:
    raw = (request.headers.get(public_share.SHARE_PASSWORD_HEADER) or "").strip()
    return raw or None


def _preferred_lang(request: Request) -> str:
    raw = (request.headers.get("accept-language") or "").strip().lower()
    if raw.startswith("de") or ",de" in raw:
        return "de"
    return "en"


class DashboardInstallBody(BaseModel):
    """Which bundle kinds to apply ``schema_sql`` for (nothing runs until you pick)."""

    kinds: list[str] = Field(default_factory=list)


class DashboardFromTemplateBody(BaseModel):
    kind: str = Field(default="custom", max_length=64)
    template_id: str | None = Field(default=None, max_length=64)
    title: str = Field(default="", max_length=500)
    ui_layout: dict[str, Any] = Field(default_factory=dict)
    initial_data: dict[str, Any] | None = Field(default=None)


class DashboardPinBlockBody(BaseModel):
    source_dashboard_id: str = Field(..., min_length=36, max_length=36)
    source_block_id: str = Field(..., min_length=1, max_length=120)
    parent_block_id: str | None = Field(default=None, max_length=120)
    title: str | None = Field(default=None, max_length=200)


@router.get("/install-status")
async def dashboard_install_status(request: Request):
    """Schema state plus ``kind_catalog`` from ``dashboard/**/dashboard.kind.json``."""
    from apps.backend.dashboard.bundle import kind_catalog, kinds_with_schema_sql, kinds_with_templates

    user = await get_current_user(request)
    installed = dashboard_tables_exist()
    cat = kind_catalog()
    template_kinds = kinds_with_templates()
    installed_kinds: list[str] | None = None
    if installed:
        tid = db.user_tenant_id(user.id)
        installed_kinds = dashboard_db.tenant_installed_template_kinds(tid)
    return {
        "ok": True,
        "schema_installed": installed,
        "kind_catalog": cat,
        "schema_install_offers": kinds_with_schema_sql() if not installed else [],
        "template_kinds": template_kinds,
        "installed_template_kinds": installed_kinds,
    }


@router.post("/install")
async def dashboard_install(request: Request, body: DashboardInstallBody):
    """Apply ``schema_sql`` only for ``body.kinds`` — does not create dashboard rows."""
    user = await get_current_user(request)
    if dashboard_tables_exist():
        return {"ok": True, "already": True}
    kinds = [str(k).strip().lower() for k in body.kinds if str(k).strip()]
    if not kinds:
        raise HTTPException(
            status_code=400,
            detail="select at least one kind (body.kinds) to install schema for; nothing is installed by default",
        )
    try:
        ensure_dashboard_schema(kinds)
    except FileNotFoundError as e:
        raise HTTPException(status_code=500, detail=http_500_detail(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=http_500_detail(e)) from e
    tid = db.user_tenant_id(user.id)
    dashboard_db.tenant_merge_installed_template_kinds(tid, kinds)
    return {"ok": True, "already": False}


@router.post("/install-templates")
async def dashboard_install_templates(request: Request, body: DashboardInstallBody):
    """Install more template kinds for this tenant (idempotent DDL + merge). Requires base schema."""
    _require_schema()
    user = await get_current_user(request)
    kinds = [str(k).strip().lower() for k in body.kinds if str(k).strip()]
    if not kinds:
        raise HTTPException(
            status_code=400,
            detail="send at least one kind in body.kinds",
        )
    try:
        ensure_dashboard_schema(kinds)
    except FileNotFoundError as e:
        raise HTTPException(status_code=500, detail=http_500_detail(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=http_500_detail(e)) from e
    tid = db.user_tenant_id(user.id)
    dashboard_db.tenant_merge_installed_template_kinds(tid, kinds)
    merged = dashboard_db.tenant_installed_template_kinds(tid)
    return {"ok": True, "installed_template_kinds": merged}


@router.get("/upload-limits")
async def dashboard_upload_limits(request: Request):
    """Effective max size and MIME allowlist (env + operator DB overrides)."""
    _require_schema()
    await get_current_user(request)
    return {
        "ok": True,
        "max_file_bytes": effective_dashboard_upload_max_bytes(),
        "allowed_mime": sorted(effective_dashboard_upload_mime()),
    }


@router.get("/shared/{token}")
async def get_shared_dashboard(token: str, request: Request):
    """Public read-only dashboard view via share token (no auth)."""
    _require_schema()
    raw = (token or "").strip()
    if len(raw) < 16:
        raise HTTPException(status_code=404, detail="share not found")
    result = public_share.public_share_get_dashboard(
        raw, password=_share_password_from_request(request)
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
    _require_schema()
    raw = (token or "").strip()
    if len(raw) < 16:
        raise HTTPException(status_code=404, detail="file not found")
    pw = _share_password_from_request(request)
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
    _require_schema()
    user = await get_current_user(request)
    tid = db.user_tenant_id(user.id)
    meta = files_db.file_get_with_access(file_id, user.id, tid)
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
    _require_schema()
    user = await get_current_user(request)
    tid = db.user_tenant_id(user.id)
    rel = files_db.file_delete_with_access(file_id, user.id, tid)
    if rel is None:
        raise HTTPException(status_code=404, detail="file not found")
    file_storage.unlink_if_exists(config.dashboard_upload_dir(), rel)
    return {"ok": True, "deleted": True}


@router.post("/{dashboard_id}/files")
async def dashboard_file_upload(
    request: Request, dashboard_id: uuid.UUID, file: UploadFile = File(...)
):
    _require_schema()
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

    try:
        row = files_db.file_insert(
            tenant_id=tid,
            owner_user_id=user.id,
            dashboard_id=dashboard_id,
            storage_relpath=relpath,
            content_type=sniff,
            size_bytes=len(data),
            original_name=name,
        )
    except Exception:
        file_storage.unlink_if_exists(config.dashboard_upload_dir(), relpath)
        raise

    return {
        "ok": True,
        "file": {
            "id": row["id"],
            "dashboard_id": row["dashboard_id"],
            "content_type": row["content_type"],
            "size_bytes": row["size_bytes"],
            "gallery_ref": f"wsfile:{row['id']}",
        },
    }


@router.get("")
async def list_dashboards(request: Request):
    from apps.backend.dashboard.bundle import (
        kind_catalog,
        kinds_with_schema_sql,
        kinds_with_templates,
        template_catalog,
        template_ids_with_templates,
    )

    user = await get_current_user(request)
    cat = template_catalog()
    template_kinds = kinds_with_templates()
    template_ids = template_ids_with_templates()
    if not dashboard_tables_exist():
        return {
            "ok": True,
            "dashboards": [],
            "schema_installed": False,
            "kind_catalog": kind_catalog(),
            "template_catalog": cat,
            "schema_install_offers": kinds_with_schema_sql(),
            "template_kinds": template_kinds,
            "template_ids": template_ids,
            "installed_template_kinds": [],
        }
    tid = db.user_tenant_id(user.id)
    items = dashboard_db.dashboard_list(user.id, tid)
    installed_kinds = dashboard_db.tenant_installed_template_kinds(tid)
    return {
        "ok": True,
        "dashboards": items,
        "schema_installed": True,
        "kind_catalog": kind_catalog(),
        "template_catalog": cat,
        "schema_install_offers": [],
        "template_kinds": template_kinds,
        "template_ids": template_ids,
        "installed_template_kinds": installed_kinds,
    }


@router.get("/templates/catalog")
async def list_template_catalog(request: Request):
    """Gallery templates (``template_id`` primary; ``kind`` legacy mirror)."""
    from apps.backend.dashboard.bundle import template_catalog

    await get_current_user(request)
    return {"ok": True, "templates": template_catalog()}


@router.post("")
async def create_dashboard(request: Request, body: DashboardCreateBody):
    from apps.backend.dashboard.create_helpers import resolve_create_target

    _require_schema()
    user = await get_current_user(request)
    tid = db.user_tenant_id(user.id)
    kind, template_id, err = resolve_create_target(
        template_id=body.template_id,
        kind=body.kind,
    )
    if err:
        raise HTTPException(status_code=400, detail=err)
    row = dashboard_db.dashboard_create(
        user.id,
        tid,
        kind=kind,
        template_id=template_id,
        title=body.title,
        ui_layout=body.ui_layout,
        data=body.data,
    )
    lang = _preferred_lang(request)
    return {"ok": True, "dashboard": attach_onboarding(row, lang)}


@router.post("/from-template")
async def create_dashboard_from_template(request: Request, body: DashboardFromTemplateBody):
    """Create a new dashboard from an exported layout snapshot (copy, not live sync)."""
    from apps.backend.dashboard.create_helpers import resolve_create_target

    _require_schema()
    user = await get_current_user(request)
    tid = db.user_tenant_id(user.id)
    kind, template_id, cerr = resolve_create_target(
        template_id=body.template_id,
        kind=body.kind,
    )
    if cerr:
        raise HTTPException(status_code=400, detail=cerr)
    ul, dt, err = validate_template_import(
        kind=kind,
        template_id=template_id,
        ui_layout=body.ui_layout,
        data=body.initial_data,
    )
    if err:
        raise HTTPException(status_code=400, detail=err)
    row = dashboard_db.dashboard_create(
        user.id,
        tid,
        kind=kind,
        template_id=template_id,
        title=body.title,
        ui_layout=ul,
        data=dt,
    )
    lang = _preferred_lang(request)
    return {"ok": True, "dashboard": attach_onboarding(row, lang)}


@router.get("/kinds/{kind}/onboarding")
async def get_kind_onboarding(request: Request, kind: str):
    """Localized onboarding manifest for a dashboard kind (no row required)."""
    _require_schema()
    await get_current_user(request)
    ob = onboarding_for_kind(kind, _preferred_lang(request))
    if not ob:
        raise HTTPException(status_code=404, detail="no onboarding for this kind")
    return {"ok": True, "onboarding": ob}


@router.get("/{dashboard_id}/members")
async def list_dashboard_members(request: Request, dashboard_id: uuid.UUID):
    _require_schema()
    user = await get_current_user(request)
    tid = db.user_tenant_id(user.id)
    acc = dashboard_db.dashboard_access(user.id, tid, dashboard_id)
    if acc is None:
        raise HTTPException(status_code=404, detail="dashboard not found")
    if not dashboard_db.dashboard_can_manage_members(user.id, tid, dashboard_id):
        raise HTTPException(status_code=403, detail="only owner or co-owner can list members")
    items = dashboard_db.members_list(user.id, tid, dashboard_id)
    return {"ok": True, "members": items}


@router.post("/{dashboard_id}/members")
async def add_dashboard_member(
    request: Request, dashboard_id: uuid.UUID, body: DashboardMemberAddBody
):
    _require_schema()
    user = await get_current_user(request)
    tid = db.user_tenant_id(user.id)
    if not dashboard_db.dashboard_can_manage_members(user.id, tid, dashboard_id):
        raise HTTPException(status_code=403, detail="only owner or co-owner can add members")
    target = get_user_by_email(body.email.strip().lower())
    if target is None:
        raise HTTPException(status_code=404, detail="user not found for this email")
    if db.user_tenant_id(target.id) != tid:
        raise HTTPException(status_code=400, detail="user must be in the same tenant")
    role = (body.role or "viewer").strip().lower()
    if role not in ("viewer", "editor", "co_owner"):
        raise HTTPException(status_code=400, detail="role must be viewer, editor, or co_owner")
    ok = dashboard_db.member_add(user.id, tid, dashboard_id, target.id, role)
    if not ok:
        raise HTTPException(status_code=400, detail="could not add member")
    return {"ok": True, "members": dashboard_db.members_list(user.id, tid, dashboard_id)}


@router.delete("/{dashboard_id}/members/{member_user_id}")
async def remove_dashboard_member(
    request: Request, dashboard_id: uuid.UUID, member_user_id: uuid.UUID
):
    _require_schema()
    user = await get_current_user(request)
    tid = db.user_tenant_id(user.id)
    if not dashboard_db.dashboard_can_manage_members(user.id, tid, dashboard_id):
        raise HTTPException(status_code=403, detail="only owner or co-owner can remove members")
    if not dashboard_db.member_remove(user.id, tid, dashboard_id, member_user_id):
        raise HTTPException(status_code=404, detail="member not found")
    return {"ok": True, "removed": True}


@router.get("/{dashboard_id}/block-shares")
async def list_dashboard_block_shares(request: Request, dashboard_id: uuid.UUID):
    _require_schema()
    user = await get_current_user(request)
    tid = db.user_tenant_id(user.id)
    if not dashboard_db.dashboard_can_manage_members(user.id, tid, dashboard_id):
        raise HTTPException(status_code=403, detail="only owner or co-owner can list block shares")
    items = dashboard_db.block_share_grants_list(user.id, tid, dashboard_id)
    return {"ok": True, "grants": items}


@router.post("/{dashboard_id}/block-shares")
async def upsert_dashboard_block_share(
    request: Request, dashboard_id: uuid.UUID, body: DashboardBlockShareBody
):
    _require_schema()
    user = await get_current_user(request)
    tid = db.user_tenant_id(user.id)
    target = get_user_by_email(body.email.strip().lower())
    if target is None:
        raise HTTPException(status_code=404, detail="user not found for this email")
    perm = (body.permission or "view").strip().lower()
    if perm not in ("view", "edit"):
        raise HTTPException(status_code=400, detail="permission must be view or edit")
    ok = dashboard_db.block_share_grant_upsert(
        user.id,
        tid,
        dashboard_id,
        viewer_user_id=target.id,
        block_ids=body.block_ids,
        permission=perm,
    )
    if not ok:
        raise HTTPException(
            status_code=400,
            detail="could not save (check block ids exist in layout, not owner email, same tenant)",
        )
    items = dashboard_db.block_share_grants_list(user.id, tid, dashboard_id)
    return {"ok": True, "grants": items}


@router.delete("/{dashboard_id}/block-shares/{viewer_user_id}")
async def delete_dashboard_block_share(
    request: Request, dashboard_id: uuid.UUID, viewer_user_id: uuid.UUID
):
    _require_schema()
    user = await get_current_user(request)
    tid = db.user_tenant_id(user.id)
    if not dashboard_db.dashboard_can_manage_members(user.id, tid, dashboard_id):
        raise HTTPException(status_code=403, detail="only owner or co-owner can remove block shares")
    if not dashboard_db.block_share_grant_delete(user.id, tid, dashboard_id, viewer_user_id):
        raise HTTPException(status_code=404, detail="grant not found")
    return {"ok": True, "removed": True}


@router.get("/{dashboard_id}/public-shares")
async def list_dashboard_public_shares(request: Request, dashboard_id: uuid.UUID):
    _require_schema()
    user = await get_current_user(request)
    tid = db.user_tenant_id(user.id)
    if not dashboard_db.dashboard_can_manage_members(user.id, tid, dashboard_id):
        raise HTTPException(status_code=403, detail="only owner or co-owner can list public shares")
    items = public_share.public_share_list(user.id, tid, dashboard_id)
    return {"ok": True, "shares": items}


@router.post("/{dashboard_id}/public-shares")
async def create_dashboard_public_share(
    request: Request, dashboard_id: uuid.UUID, body: DashboardPublicShareCreateBody
):
    _require_schema()
    user = await get_current_user(request)
    tid = db.user_tenant_id(user.id)
    expires_at = None
    if body.expires_at:
        raw_exp = body.expires_at.strip()
        if raw_exp:
            try:
                expires_at = datetime.fromisoformat(raw_exp.replace("Z", "+00:00"))
            except ValueError as e:
                raise HTTPException(status_code=400, detail="expires_at must be ISO-8601") from e
    if body.password is not None and body.password.strip() and len(body.password.strip()) < 4:
        raise HTTPException(status_code=400, detail="password must be at least 4 characters")
    created = public_share.public_share_create(
        user.id,
        tid,
        dashboard_id,
        block_ids=body.block_ids,
        label=body.label,
        expires_at=expires_at,
        password=body.password,
    )
    if created is None:
        raise HTTPException(
            status_code=400,
            detail="could not create share (check block ids or permissions)",
        )
    raw_token, meta = created
    share_url = f"/app/dashboard/shared?t={raw_token}"
    return {
        "ok": True,
        "share": {**meta, "url_path": share_url},
        "token": raw_token,
    }


@router.delete("/{dashboard_id}/public-shares/{share_id}")
async def revoke_dashboard_public_share(
    request: Request, dashboard_id: uuid.UUID, share_id: uuid.UUID
):
    _require_schema()
    user = await get_current_user(request)
    tid = db.user_tenant_id(user.id)
    if not dashboard_db.dashboard_can_manage_members(user.id, tid, dashboard_id):
        raise HTTPException(status_code=403, detail="only owner or co-owner can revoke public shares")
    if not public_share.public_share_revoke(user.id, tid, dashboard_id, share_id):
        raise HTTPException(status_code=404, detail="share not found")
    return {"ok": True, "revoked": True}


@router.get("/{dashboard_id}/export-template")
async def export_dashboard_template(request: Request, dashboard_id: uuid.UUID):
    """Export layout + data as an importable template snapshot."""
    _require_schema()
    user = await get_current_user(request)
    tid = db.user_tenant_id(user.id)
    row = dashboard_db.dashboard_get(user.id, tid, dashboard_id)
    if not row:
        raise HTTPException(status_code=404, detail="dashboard not found")
    payload = export_template_payload(
        kind=str(row.get("kind") or "custom"),
        template_id=str(row.get("template_id") or "") or None,
        title=str(row.get("title") or ""),
        ui_layout=row.get("ui_layout") if isinstance(row.get("ui_layout"), dict) else {},
        data=row.get("data") if isinstance(row.get("data"), dict) else {},
    )
    return {"ok": True, "template": payload}


@router.get("/{dashboard_id}/blocks/{block_id}/render")
async def render_dashboard_block(
    request: Request, dashboard_id: uuid.UUID, block_id: str
):
    """Resolve one block + data slice for dashboard_ref rendering (ACL enforced)."""
    _require_schema()
    user = await get_current_user(request)
    tid = db.user_tenant_id(user.id)
    payload = render_block_from_dashboard(user.id, tid, dashboard_id, block_id)
    if not payload:
        raise HTTPException(status_code=404, detail="block not found or access denied")
    return {"ok": True, **payload}


@router.post("/{dashboard_id}/pin-block")
async def pin_dashboard_block(
    request: Request, dashboard_id: uuid.UUID, body: DashboardPinBlockBody
):
    """Add a dashboard_ref block pointing at a block from another accessible dashboard."""
    _require_schema()
    user = await get_current_user(request)
    tid = db.user_tenant_id(user.id)
    try:
        source_id = uuid.UUID(body.source_dashboard_id.strip())
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid source_dashboard_id")
    result = pin_block_to_dashboard(
        user.id,
        tid,
        dashboard_id,
        source_dashboard_id=source_id,
        source_block_id=body.source_block_id,
        parent_block_id=body.parent_block_id,
        title=body.title,
    )
    if not result:
        raise HTTPException(
            status_code=400,
            detail="could not pin (check edit access on target and read access on source block)",
        )
    return result


@router.get("/{dashboard_id}/layout-proposals/active")
async def get_active_layout_proposals(request: Request, dashboard_id: uuid.UUID):
    """Latest non-expired layout proposal set for this user and dashboard."""
    _require_schema()
    user = await get_current_user(request)
    tid = db.user_tenant_id(user.id)
    row = dashboard_db.dashboard_get(user.id, tid, dashboard_id)
    if not row:
        raise HTTPException(status_code=404, detail="dashboard not found")
    pset = get_latest_proposal_set(tenant_id=tid, user_id=user.id, dashboard_id=dashboard_id)
    if pset is None:
        return {"ok": True, "proposal_set": None}
    return {"ok": True, "proposal_set": pset.to_dict(include_layouts=True)}


@router.get("/{dashboard_id}/layout-proposals/{set_id}")
async def get_layout_proposal_set(
    request: Request, dashboard_id: uuid.UUID, set_id: str
):
    _require_schema()
    user = await get_current_user(request)
    tid = db.user_tenant_id(user.id)
    row = dashboard_db.dashboard_get(user.id, tid, dashboard_id)
    if not row:
        raise HTTPException(status_code=404, detail="dashboard not found")
    pset = get_proposal_set(
        tenant_id=tid,
        user_id=user.id,
        dashboard_id=dashboard_id,
        set_id=set_id.strip(),
    )
    if pset is None:
        raise HTTPException(status_code=404, detail="proposal set not found or expired")
    return {"ok": True, "proposal_set": pset.to_dict(include_layouts=True)}


@router.post("/{dashboard_id}/layout-proposals/{set_id}/{proposal_id}/apply")
async def apply_layout_proposal_endpoint(
    request: Request,
    dashboard_id: uuid.UUID,
    set_id: str,
    proposal_id: str,
):
    _require_schema()
    user = await get_current_user(request)
    tid = db.user_tenant_id(user.id)
    updated, err = apply_layout_proposal(
        tenant_id=tid,
        user_id=user.id,
        dashboard_id=dashboard_id,
        set_id=set_id.strip(),
        proposal_id=proposal_id.strip(),
    )
    if err:
        code = 404 if "not found" in err.lower() else 400
        raise HTTPException(status_code=code, detail=err)
    return {"ok": True, "dashboard": attach_onboarding(updated, _preferred_lang(request))}


@router.get("/{dashboard_id}")
async def get_dashboard(request: Request, dashboard_id: uuid.UUID):
    _require_schema()
    user = await get_current_user(request)
    tid = db.user_tenant_id(user.id)
    row = dashboard_db.dashboard_get(user.id, tid, dashboard_id)
    if not row:
        raise HTTPException(status_code=404, detail="dashboard not found")
    return {"ok": True, "dashboard": attach_onboarding(row, _preferred_lang(request))}


@router.patch("/{dashboard_id}")
async def patch_dashboard(
    request: Request, dashboard_id: uuid.UUID, body: DashboardPatchBody
):
    _require_schema()
    user = await get_current_user(request)
    tid = db.user_tenant_id(user.id)
    row = dashboard_db.dashboard_update(
        user.id,
        tid,
        dashboard_id,
        title=body.title,
        ui_layout=body.ui_layout,
        data=body.data,
    )
    if not row:
        raise HTTPException(status_code=404, detail="dashboard not found")
    return {"ok": True, "dashboard": row}


@router.delete("/{dashboard_id}")
async def delete_dashboard(request: Request, dashboard_id: uuid.UUID):
    _require_schema()
    user = await get_current_user(request)
    tid = db.user_tenant_id(user.id)
    if not dashboard_db.dashboard_delete(user.id, tid, dashboard_id):
        raise HTTPException(status_code=404, detail="dashboard not found")
    return {"ok": True, "deleted": True}
