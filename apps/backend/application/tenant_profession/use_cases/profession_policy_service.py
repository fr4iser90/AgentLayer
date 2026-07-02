"""Profession RBAC — policy resolution with persistence (Task 05)."""

from __future__ import annotations

import uuid
from typing import Any

from apps.backend.domain.tenant_profession.policy import (
    CAP_KNOWLEDGE_SEARCH,
    DEFAULT_DEPARTMENTS,
    DEFAULT_PROFESSION_ROLES,
    EffectiveProfessionPolicy,
    _KIND_CAPABILITIES,
    _TENANT_ADMIN_CAPS,
    content_visible_to_policy,
)
from apps.backend.infrastructure.db import db
from apps.backend.infrastructure.db.tenant_profession_persistence import tenant_content_get_by_source_uri


def ensure_tenant_profession_defaults(tenant_id: int) -> None:
    if db.profession_roles_count(tenant_id) > 0:
        return
    for slug, name in DEFAULT_DEPARTMENTS:
        if not db.department_get_by_slug(tenant_id, slug):
            db.department_insert(tenant_id, slug, name)
    for slug, name, kind, cats in DEFAULT_PROFESSION_ROLES:
        if not db.profession_role_get_by_slug(tenant_id, slug):
            db.profession_role_insert(tenant_id, slug, name, kind, list(cats))


def effective_policy(user_id: uuid.UUID, tenant_id: int) -> EffectiveProfessionPolicy:
    ensure_tenant_profession_defaults(tenant_id)
    is_admin = db.user_is_tenant_admin(user_id, tenant_id)
    site_admin = db.user_site_role(user_id) == "site_admin"
    if site_admin:
        is_admin = True
    assignment = db.profession_assignment_get(user_id, tenant_id)
    qualifications = tuple(db.qualifications_list(user_id, tenant_id))

    if is_admin:
        dept_slug = assignment.get("department_slug") if assignment else None
        dept_name = assignment.get("department_name") if assignment else None
        role_slug = assignment.get("profession_role_slug") if assignment else None
        role_name = assignment.get("profession_role_name") if assignment else None
        role_kind = str(assignment.get("role_kind") if assignment else "domain_admin")
        cats = assignment.get("content_categories") if assignment else []
        return EffectiveProfessionPolicy(
            tenant_id=tenant_id,
            user_id=user_id,
            is_tenant_admin=True,
            profession_role_slug=role_slug,
            profession_role_name=role_name,
            role_kind=role_kind,
            department_slug=dept_slug,
            department_name=dept_name,
            content_categories=tuple(str(c) for c in (cats or [])),
            capabilities=_TENANT_ADMIN_CAPS,
            qualifications=qualifications,
        )

    if not assignment:
        return EffectiveProfessionPolicy(
            tenant_id=tenant_id,
            user_id=user_id,
            is_tenant_admin=False,
            profession_role_slug=None,
            profession_role_name=None,
            role_kind="end_user",
            department_slug=None,
            department_name=None,
            content_categories=(),
            capabilities=frozenset({CAP_KNOWLEDGE_SEARCH}),
            qualifications=qualifications,
        )

    kind = str(assignment.get("role_kind") or "end_user")
    caps = _KIND_CAPABILITIES.get(kind, frozenset({CAP_KNOWLEDGE_SEARCH}))
    cats = assignment.get("content_categories") or []
    return EffectiveProfessionPolicy(
        tenant_id=tenant_id,
        user_id=user_id,
        is_tenant_admin=False,
        profession_role_slug=str(assignment.get("profession_role_slug") or ""),
        profession_role_name=str(assignment.get("profession_role_name") or ""),
        role_kind=kind,
        department_slug=assignment.get("department_slug"),
        department_name=assignment.get("department_name"),
        content_categories=tuple(str(c) for c in cats),
        capabilities=caps,
        qualifications=qualifications,
    )


def filter_rag_hits(hits: list[dict[str, Any]], policy: EffectiveProfessionPolicy) -> list[dict[str, Any]]:
    if not hits:
        return hits
    out: list[dict[str, Any]] = []
    cache: dict[str, dict[str, Any] | None] = {}
    for hit in hits:
        uri = str(hit.get("source_uri") or "").strip()
        if not uri.startswith("tenant-content/"):
            out.append(hit)
            continue
        if uri not in cache:
            cache[uri] = tenant_content_get_by_source_uri(policy.tenant_id, uri)
        content = cache[uri]
        if content and content_visible_to_policy(content, policy):
            out.append(hit)
    return out


def build_profession_capsule(user_id: uuid.UUID, tenant_id: int) -> str:
    policy = effective_policy(user_id, tenant_id)
    pub = policy.to_public_dict()
    lines = [
        "## Caller profession context (compact)",
        f"- Role: {pub.get('profession_role_name') or pub.get('role_kind') or 'end_user'}",
    ]
    if pub.get("department_name"):
        lines.append(f"- Department: {pub['department_name']}")
    if pub.get("content_categories"):
        lines.append(f"- Allowed content categories: {', '.join(pub['content_categories'])}")
    if pub.get("qualifications_valid"):
        lines.append(f"- Valid qualifications: {', '.join(pub['qualifications_valid'])}")
    lines.append(
        "- If retrieved content requires qualifications the caller lacks, refuse and name the missing qualification."
    )
    lines.append(
        "- Respect target profession/department tags — do not generalize restricted notes to other roles."
    )
    return "\n".join(lines)
