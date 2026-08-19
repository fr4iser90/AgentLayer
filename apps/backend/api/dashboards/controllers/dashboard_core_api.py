"""Dashboard CRUD, templates, blocks, and layout proposal endpoints."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Request

from apps.backend.api.dashboards.controllers.dashboard_common import (
    DashboardCreateBody,
    DashboardFromTemplateBody,
    DashboardPatchBody,
    DashboardPinBlockBody,
    preferred_lang,
    require_dashboard_schema,
)
from apps.backend.application.dashboards.use_cases.dashboard_controller_services import db
from apps.backend.application.dashboards.use_cases.dashboard_controller_services import dashboard_db
from apps.backend.application.dashboards.use_cases.dashboard_controller_services import render_block_from_dashboard
from apps.backend.application.dashboards.use_cases.dashboard_controller_services import dashboard_tables_exist
from apps.backend.application.dashboards.use_cases.dashboard_controller_services import apply_layout_proposal, get_latest_proposal_set, get_proposal_set
from apps.backend.application.dashboards.use_cases.dashboard_controller_services import pin_block_to_dashboard
from apps.backend.application.dashboards.use_cases.dashboard_controller_services import attach_onboarding, onboarding_for_kind
from apps.backend.application.dashboards.use_cases.dashboard_controller_services import export_template_payload, validate_template_import
from apps.backend.application.identity.use_cases.request_auth import get_current_user

router = APIRouter()

@router.get("")
async def list_dashboards(request: Request):
    from apps.backend.application.dashboards.use_cases.dashboard_controller_services import (
        kind_catalog,
        kinds_with_schema_sql,
        kinds_with_templates,
        template_catalog,
        template_ids_with_templates,
    )

    user = await get_current_user(request)
    tid = db.user_tenant_id(user.id)
    from apps.backend.domain.tenant_capability.policy import tenant_allowed_dashboard_kinds

    allowed = tenant_allowed_dashboard_kinds(tid)
    cat = template_catalog(tenant_id=tid)
    if allowed is None:
        template_kinds = kinds_with_templates()
        template_ids = template_ids_with_templates()
        schema_offers = kinds_with_schema_sql()
    else:
        template_kinds = [k for k in kinds_with_templates() if k in allowed]
        template_ids = [
            tid_
            for tid_ in template_ids_with_templates()
            if any(str(r.get("template_id") or "") == tid_ for r in cat)
        ]
        schema_offers = [k for k in kinds_with_schema_sql() if k in allowed]
    if not dashboard_tables_exist():
        return {
            "ok": True,
            "dashboards": [],
            "schema_installed": False,
            "kind_catalog": kind_catalog(tenant_id=tid),
            "template_catalog": cat,
            "schema_install_offers": schema_offers,
            "template_kinds": template_kinds,
            "template_ids": template_ids,
            "installed_template_kinds": [],
        }
    items = dashboard_db.dashboard_list(user.id, tid)
    installed_kinds = dashboard_db.tenant_installed_template_kinds(tid)
    return {
        "ok": True,
        "dashboards": items,
        "schema_installed": True,
        "kind_catalog": kind_catalog(tenant_id=tid),
        "template_catalog": cat,
        "schema_install_offers": [],
        "template_kinds": template_kinds,
        "template_ids": template_ids,
        "installed_template_kinds": installed_kinds,
    }


@router.get("/templates/catalog")
async def list_template_catalog(request: Request):
    """Gallery templates (``template_id`` primary; ``kind`` legacy mirror)."""
    from apps.backend.application.dashboards.use_cases.dashboard_controller_services import template_catalog

    user = await get_current_user(request)
    tid = db.user_tenant_id(user.id)
    return {"ok": True, "templates": template_catalog(tenant_id=tid)}


@router.post("")
async def create_dashboard(request: Request, body: DashboardCreateBody):
    from apps.backend.application.dashboards.use_cases.dashboard_controller_services import resolve_create_target
    from apps.backend.application.dashboards.use_cases.dashboard_controller_services import validate_kind_for_tenant

    require_dashboard_schema()
    user = await get_current_user(request)
    tid = db.user_tenant_id(user.id)
    kind, template_id, err = resolve_create_target(
        template_id=body.template_id,
        kind=body.kind,
    )
    if err:
        raise HTTPException(status_code=400, detail=err)
    kerr = validate_kind_for_tenant(tid, kind)
    if kerr:
        raise HTTPException(status_code=403, detail=kerr)
    from apps.backend.application.dashboards.use_cases.dashboard_controller_services import (
        validate_structure_edit_for_user,
    )

    serr = validate_structure_edit_for_user(tid, user.id)
    if serr:
        raise HTTPException(status_code=403, detail=serr)
    row = dashboard_db.dashboard_create(
        user.id,
        tid,
        kind=kind,
        template_id=template_id,
        title=body.title,
        ui_layout=body.ui_layout,
        data=body.data,
    )
    lang = preferred_lang(request)
    return {"ok": True, "dashboard": attach_onboarding(row, lang)}


@router.post("/from-template")
async def create_dashboard_from_template(request: Request, body: DashboardFromTemplateBody):
    """Create a new dashboard from an exported layout snapshot (copy, not live sync)."""
    from apps.backend.application.dashboards.use_cases.dashboard_controller_services import resolve_create_target
    from apps.backend.application.dashboards.use_cases.dashboard_controller_services import (
        validate_kind_for_tenant,
        validate_structure_edit_for_user,
    )

    require_dashboard_schema()
    user = await get_current_user(request)
    tid = db.user_tenant_id(user.id)
    kind, template_id, cerr = resolve_create_target(
        template_id=body.template_id,
        kind=body.kind,
    )
    if cerr:
        raise HTTPException(status_code=400, detail=cerr)
    kerr = validate_kind_for_tenant(tid, kind)
    if kerr:
        raise HTTPException(status_code=403, detail=kerr)
    serr = validate_structure_edit_for_user(tid, user.id)
    if serr:
        raise HTTPException(status_code=403, detail=serr)
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
    lang = preferred_lang(request)
    return {"ok": True, "dashboard": attach_onboarding(row, lang)}


@router.get("/kinds/{kind}/onboarding")
async def get_kind_onboarding(request: Request, kind: str):
    """Localized onboarding manifest for a dashboard kind (no row required)."""
    require_dashboard_schema()
    await get_current_user(request)
    ob = onboarding_for_kind(kind, preferred_lang(request))
    if not ob:
        raise HTTPException(status_code=404, detail="no onboarding for this kind")
    return {"ok": True, "onboarding": ob}

@router.get("/{dashboard_id}/export-template")
async def export_dashboard_template(request: Request, dashboard_id: uuid.UUID):
    """Export layout + data as an importable template snapshot."""
    require_dashboard_schema()
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
    require_dashboard_schema()
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
    require_dashboard_schema()
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
    require_dashboard_schema()
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
    require_dashboard_schema()
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
    require_dashboard_schema()
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
    return {"ok": True, "dashboard": attach_onboarding(updated, preferred_lang(request))}


@router.get("/{dashboard_id}")
async def get_dashboard(request: Request, dashboard_id: uuid.UUID):
    require_dashboard_schema()
    user = await get_current_user(request)
    tid = db.user_tenant_id(user.id)
    row = dashboard_db.dashboard_get(user.id, tid, dashboard_id)
    if not row:
        raise HTTPException(status_code=404, detail="dashboard not found")
    return {"ok": True, "dashboard": attach_onboarding(row, preferred_lang(request))}


@router.patch("/{dashboard_id}")
async def patch_dashboard(
    request: Request, dashboard_id: uuid.UUID, body: DashboardPatchBody
):
    from apps.backend.application.dashboards.use_cases.dashboard_controller_services import (
        validate_structure_edit_for_user,
    )

    require_dashboard_schema()
    user = await get_current_user(request)
    tid = db.user_tenant_id(user.id)
    structure_err = validate_structure_edit_for_user(tid, user.id)
    if structure_err and (body.title is not None or body.ui_layout is not None):
        raise HTTPException(status_code=403, detail=structure_err)
    row = dashboard_db.dashboard_update(
        user.id,
        tid,
        dashboard_id,
        title=body.title if not structure_err else None,
        ui_layout=body.ui_layout if not structure_err else None,
        data=body.data,
    )
    if not row:
        raise HTTPException(status_code=404, detail="dashboard not found")
    return {"ok": True, "dashboard": row}


@router.delete("/{dashboard_id}")
async def delete_dashboard(request: Request, dashboard_id: uuid.UUID):
    from apps.backend.application.dashboards.use_cases.dashboard_controller_services import (
        validate_structure_edit_for_user,
    )

    require_dashboard_schema()
    user = await get_current_user(request)
    tid = db.user_tenant_id(user.id)
    serr = validate_structure_edit_for_user(tid, user.id)
    if serr:
        raise HTTPException(status_code=403, detail=serr)
    if not dashboard_db.dashboard_delete(user.id, tid, dashboard_id):
        raise HTTPException(status_code=404, detail="dashboard not found")
    return {"ok": True, "deleted": True}
