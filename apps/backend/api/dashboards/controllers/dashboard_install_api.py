"""Dashboard schema installation and upload limit endpoints."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from apps.backend.api.dashboards.controllers.dashboard_common import DashboardInstallBody, require_dashboard_schema
from apps.backend.application.dashboards.use_cases.dashboard_controller_services import db
from apps.backend.application.dashboards.use_cases.dashboard_controller_services import dashboard_db
from apps.backend.application.dashboards.use_cases.dashboard_controller_services import ensure_dashboard_schema, dashboard_tables_exist
from apps.backend.application.identity.use_cases.request_auth import get_current_user
from apps.backend.application.dashboards.use_cases.dashboard_controller_services import http_500_detail
from apps.backend.application.dashboards.use_cases.dashboard_controller_services import effective_dashboard_upload_max_bytes, effective_dashboard_upload_mime

router = APIRouter()

@router.get("/install-status")
async def dashboard_install_status(request: Request):
    """Schema state plus ``kind_catalog`` from ``dashboard/**/dashboard.kind.json``."""
    from apps.backend.application.dashboards.use_cases.dashboard_controller_services import kind_catalog, kinds_with_schema_sql, kinds_with_templates

    user = await get_current_user(request)
    tid = db.user_tenant_id(user.id)
    from apps.backend.domain.tenant_capability.policy import tenant_allowed_dashboard_kinds

    allowed = tenant_allowed_dashboard_kinds(tid)
    installed = dashboard_tables_exist()
    cat = kind_catalog(tenant_id=tid)
    if allowed is None:
        template_kinds = kinds_with_templates()
        offers = kinds_with_schema_sql() if not installed else []
    else:
        template_kinds = [k for k in kinds_with_templates() if k in allowed]
        offers = [k for k in kinds_with_schema_sql() if k in allowed] if not installed else []
    installed_kinds: list[str] | None = None
    if installed:
        installed_kinds = dashboard_db.tenant_installed_template_kinds(tid)
    return {
        "ok": True,
        "schema_installed": installed,
        "kind_catalog": cat,
        "schema_install_offers": offers,
        "template_kinds": template_kinds,
        "installed_template_kinds": installed_kinds,
    }


@router.post("/install")
async def dashboard_install(request: Request, body: DashboardInstallBody):
    """Apply ``schema_sql`` only for ``body.kinds`` — does not create dashboard rows."""
    from apps.backend.application.dashboards.use_cases.dashboard_controller_services import validate_kind_for_tenant

    user = await get_current_user(request)
    if dashboard_tables_exist():
        return {"ok": True, "already": True}
    kinds = [str(k).strip().lower() for k in body.kinds if str(k).strip()]
    if not kinds:
        raise HTTPException(
            status_code=400,
            detail="select at least one kind (body.kinds) to install schema for; nothing is installed by default",
        )
    tid = db.user_tenant_id(user.id)
    for k in kinds:
        kerr = validate_kind_for_tenant(tid, k)
        if kerr:
            raise HTTPException(status_code=403, detail=kerr)
    try:
        ensure_dashboard_schema(kinds)
    except FileNotFoundError as e:
        raise HTTPException(status_code=500, detail=http_500_detail(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=http_500_detail(e)) from e
    dashboard_db.tenant_merge_installed_template_kinds(tid, kinds)
    return {"ok": True, "already": False}


@router.post("/install-templates")
async def dashboard_install_templates(request: Request, body: DashboardInstallBody):
    """Install more template kinds for this tenant (idempotent DDL + merge). Requires base schema."""
    from apps.backend.application.dashboards.use_cases.dashboard_controller_services import validate_kind_for_tenant

    require_dashboard_schema()
    user = await get_current_user(request)
    kinds = [str(k).strip().lower() for k in body.kinds if str(k).strip()]
    if not kinds:
        raise HTTPException(
            status_code=400,
            detail="send at least one kind in body.kinds",
        )
    tid = db.user_tenant_id(user.id)
    for k in kinds:
        kerr = validate_kind_for_tenant(tid, k)
        if kerr:
            raise HTTPException(status_code=403, detail=kerr)
    try:
        ensure_dashboard_schema(kinds)
    except FileNotFoundError as e:
        raise HTTPException(status_code=500, detail=http_500_detail(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=http_500_detail(e)) from e
    dashboard_db.tenant_merge_installed_template_kinds(tid, kinds)
    merged = dashboard_db.tenant_installed_template_kinds(tid)
    return {"ok": True, "installed_template_kinds": merged}


@router.get("/upload-limits")
async def dashboard_upload_limits(request: Request):
    """Effective max size and MIME allowlist (env + operator DB overrides)."""
    require_dashboard_schema()
    await get_current_user(request)
    return {
        "ok": True,
        "max_file_bytes": effective_dashboard_upload_max_bytes(),
        "allowed_mime": sorted(effective_dashboard_upload_mime()),
    }
