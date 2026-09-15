"""Profession RBAC — policy resolution with persistence (Task 05)."""

from __future__ import annotations

import uuid
from typing import Any

from apps.backend.domain.tenant_profession.policy import (
    CAP_KNOWLEDGE_SEARCH,
    DEFAULT_DEPARTMENTS,
    DEFAULT_PROFESSION_ROLES,
    EffectiveProfessionPolicy,
    capabilities_for_role_kind,
    _TENANT_ADMIN_CAPS,
    content_visible_to_policy,
)
from apps.backend.infrastructure.db import db
from apps.backend.infrastructure.db.tenant_profession_persistence import tenant_content_get_by_source_uri


def _union_role_capabilities(assignments: list[dict[str, Any]]) -> frozenset[str]:
    """Cumulative content capabilities across every assigned role (Weg B).

    Reads the authoritative ``capabilities`` JSONB per role. Roles without stored
    capabilities (legacy / pre-seed rows) fall back to the ``role_kind`` seed map
    so the effective set never silently shrinks.
    """
    out: set[str] = set()
    for a in assignments:
        stored = a.get("capabilities") or []
        if stored:
            for cap in stored:
                out.add(str(cap).strip().lower())
        else:
            out |= capabilities_for_role_kind(str(a.get("role_kind") or "end_user"))
    if not out:
        out = {CAP_KNOWLEDGE_SEARCH}
    return frozenset(out)


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
    assignments = db.profession_assignments_list_user(user_id, tenant_id)
    first = assignments[0] if assignments else None
    qualifications = tuple(db.qualifications_list(user_id, tenant_id))

    if is_admin:
        role_slug = first.get("profession_role_slug") if first else None
        role_name = first.get("profession_role_name") if first else None
        role_kind = str(first.get("role_kind") if first else "domain_admin")
        dept_slug = first.get("department_slug") if first else None
        dept_name = first.get("department_name") if first else None
        cats = first.get("content_categories") if first else []
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

    if not first:
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

    caps = _union_role_capabilities(assignments)
    return EffectiveProfessionPolicy(
        tenant_id=tenant_id,
        user_id=user_id,
        is_tenant_admin=False,
        profession_role_slug=str(first.get("profession_role_slug") or ""),
        profession_role_name=str(first.get("profession_role_name") or ""),
        role_kind=str(first.get("role_kind") or "end_user"),
        department_slug=first.get("department_slug"),
        department_name=first.get("department_name"),
        content_categories=tuple(str(c) for c in (first.get("content_categories") or [])),
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
