"""Organization profession RBAC API (Task 05)."""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from apps.backend.application.org.use_cases import org_profession_controller_services as prof_svc
from apps.backend.application.identity.use_cases.request_auth import (
    require_tenant_admin,
    require_tenant_member,
)

router = APIRouter()

CAP_PROFESSION_ADMIN = prof_svc.CAP_PROFESSION_ADMIN
db = prof_svc.db
effective_policy = prof_svc.effective_policy
ensure_tenant_profession_defaults = prof_svc.ensure_tenant_profession_defaults
require_capability = prof_svc.require_capability


class DepartmentBody(BaseModel):
    slug: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=256)


class ProfessionRoleBody(BaseModel):
    slug: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=256)
    role_kind: str = Field(min_length=1, max_length=32)
    content_categories: list[str] = Field(default_factory=list)


class AssignmentBody(BaseModel):
    user_id: str
    profession_role_id: str
    department_id: str | None = None


class QualificationBody(BaseModel):
    qualification_type: str = Field(min_length=1, max_length=64)
    valid_until: date | None = None
    evidence_ref: str | None = Field(default=None, max_length=512)


def _tid(user: Any) -> int:
    return db.user_tenant_id(user.id)


def _require_profession_admin(user: Any, tenant_id: int) -> None:
    policy = effective_policy(user.id, tenant_id)
    require_capability(policy, CAP_PROFESSION_ADMIN)


@router.get("/v1/org/me/profession-policy")
async def org_me_profession_policy(request: Request):
    user = await require_tenant_member(request)
    tid = _tid(user)
    ensure_tenant_profession_defaults(tid)
    return {"policy": effective_policy(user.id, tid).to_public_dict()}


@router.get("/v1/org/departments")
async def org_list_departments(request: Request):
    user = await require_tenant_admin(request)
    tid = _tid(user)
    ensure_tenant_profession_defaults(tid)
    return {"items": db.departments_list(tid)}


@router.post("/v1/org/departments")
async def org_create_department(request: Request, body: DepartmentBody):
    user = await require_tenant_admin(request)
    tid = _tid(user)
    _require_profession_admin(user, tid)
    if db.department_get_by_slug(tid, body.slug):
        raise HTTPException(status_code=409, detail="department slug already exists")
    row = db.department_insert(tid, body.slug, body.name)
    return {"department": row}


@router.get("/v1/org/profession-roles")
async def org_list_profession_roles(request: Request):
    user = await require_tenant_admin(request)
    tid = _tid(user)
    ensure_tenant_profession_defaults(tid)
    return {"items": db.profession_roles_list(tid)}


@router.post("/v1/org/profession-roles")
async def org_create_profession_role(request: Request, body: ProfessionRoleBody):
    user = await require_tenant_admin(request)
    tid = _tid(user)
    _require_profession_admin(user, tid)
    if db.profession_role_get_by_slug(tid, body.slug):
        raise HTTPException(status_code=409, detail="profession role slug already exists")
    row = db.profession_role_insert(
        tid, body.slug, body.name, body.role_kind, body.content_categories
    )
    return {"profession_role": row}


@router.get("/v1/org/profession-assignments")
async def org_list_assignments(request: Request):
    user = await require_tenant_admin(request)
    tid = _tid(user)
    ensure_tenant_profession_defaults(tid)
    return {"items": db.profession_assignments_list(tid)}


@router.put("/v1/org/profession-assignments")
async def org_upsert_assignment(request: Request, body: AssignmentBody):
    user = await require_tenant_admin(request)
    tid = _tid(user)
    _require_profession_admin(user, tid)
    try:
        uid = uuid.UUID(body.user_id.strip())
        role_id = uuid.UUID(body.profession_role_id.strip())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invalid uuid") from exc
    dept_id: uuid.UUID | None = None
    if body.department_id:
        try:
            dept_id = uuid.UUID(body.department_id.strip())
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="invalid department_id") from exc
    if not db.profession_role_get(role_id, tid):
        raise HTTPException(status_code=404, detail="profession role not found")
    if dept_id is not None and not db.department_get(dept_id, tid):
        raise HTTPException(status_code=404, detail="department not found")
    row = db.profession_assignment_upsert(uid, tid, role_id, dept_id)
    return {"assignment": row}


@router.get("/v1/org/users/{user_id}/qualifications")
async def org_list_qualifications(request: Request, user_id: str):
    admin = await require_tenant_admin(request)
    tid = _tid(admin)
    try:
        uid = uuid.UUID(user_id.strip())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invalid user_id") from exc
    return {"items": db.qualifications_list(uid, tid)}


@router.post("/v1/org/users/{user_id}/qualifications")
async def org_add_qualification(request: Request, user_id: str, body: QualificationBody):
    admin = await require_tenant_admin(request)
    tid = _tid(admin)
    _require_profession_admin(admin, tid)
    try:
        uid = uuid.UUID(user_id.strip())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invalid user_id") from exc
    row = db.qualification_insert(uid, tid, body.qualification_type, body.valid_until, body.evidence_ref)
    return {"qualification": row}


@router.delete("/v1/org/users/{user_id}/qualifications/{qualification_id}")
async def org_delete_qualification(request: Request, user_id: str, qualification_id: str):
    admin = await require_tenant_admin(request)
    tid = _tid(admin)
    _require_profession_admin(admin, tid)
    try:
        qid = uuid.UUID(qualification_id.strip())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invalid qualification_id") from exc
    if not db.qualification_delete(qid, tid):
        raise HTTPException(status_code=404, detail="qualification not found")
    return {"ok": True}
