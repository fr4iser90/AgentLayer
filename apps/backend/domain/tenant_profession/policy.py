"""Tenant profession RBAC — effective policy and content visibility (Task 05)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

from fastapi import HTTPException

from fastapi import HTTPException

CAP_KNOWLEDGE_SEARCH = "knowledge.search"
CAP_CONTENT_EDITOR = "content.editor"
CAP_CONTENT_REVIEW = "content.review"
CAP_CONTENT_PUBLISH = "content.publish"
CAP_PROFESSION_ADMIN = "profession.admin"

_KIND_CAPABILITIES: dict[str, frozenset[str]] = {
    "content_editor": frozenset({CAP_KNOWLEDGE_SEARCH, CAP_CONTENT_EDITOR}),
    "content_reviewer": frozenset({CAP_KNOWLEDGE_SEARCH, CAP_CONTENT_EDITOR, CAP_CONTENT_REVIEW}),
    "content_approver": frozenset({CAP_KNOWLEDGE_SEARCH, CAP_CONTENT_EDITOR, CAP_CONTENT_PUBLISH}),
    "domain_admin": frozenset(
        {
            CAP_KNOWLEDGE_SEARCH,
            CAP_CONTENT_EDITOR,
            CAP_CONTENT_REVIEW,
            CAP_CONTENT_PUBLISH,
            CAP_PROFESSION_ADMIN,
        }
    ),
    "end_user": frozenset({CAP_KNOWLEDGE_SEARCH}),
    "trainee": frozenset({CAP_KNOWLEDGE_SEARCH}),
}

_TENANT_ADMIN_CAPS = frozenset(
    {
        CAP_KNOWLEDGE_SEARCH,
        CAP_CONTENT_EDITOR,
        CAP_CONTENT_REVIEW,
        CAP_CONTENT_PUBLISH,
        CAP_PROFESSION_ADMIN,
    }
)

DEFAULT_DEPARTMENTS: tuple[tuple[str, str], ...] = (
    ("anesthesia", "Anesthesia"),
    ("or", "Operating room"),
)

DEFAULT_PROFESSION_ROLES: tuple[tuple[str, str, str, tuple[str, ...]], ...] = (
    ("anesthesia_nurse", "Anesthesia nurse", "end_user", ()),
    ("ota", "OTA", "end_user", ()),
    ("trainee", "Trainee", "trainee", ("onboarding",)),
    ("content_editor", "Content editor", "content_editor", ()),
    ("content_reviewer", "Content reviewer", "content_reviewer", ()),
    ("content_approver", "Content approver", "content_approver", ()),
)


@dataclass(frozen=True)
class EffectiveProfessionPolicy:
    tenant_id: int
    user_id: uuid.UUID
    is_tenant_admin: bool
    profession_role_slug: str | None
    profession_role_name: str | None
    role_kind: str
    department_slug: str | None
    department_name: str | None
    content_categories: tuple[str, ...]
    capabilities: frozenset[str]
    qualifications: tuple[dict[str, Any], ...]

    def has(self, capability: str) -> bool:
        return capability in self.capabilities

    def to_public_dict(self) -> dict[str, Any]:
        valid_q = [
            q["qualification_type"]
            for q in self.qualifications
            if _qualification_valid(q)
        ]
        expired_q = [
            q["qualification_type"]
            for q in self.qualifications
            if not _qualification_valid(q)
        ]
        return {
            "tenant_id": self.tenant_id,
            "profession_role_slug": self.profession_role_slug,
            "profession_role_name": self.profession_role_name,
            "role_kind": self.role_kind,
            "department_slug": self.department_slug,
            "department_name": self.department_name,
            "content_categories": list(self.content_categories),
            "capabilities": sorted(self.capabilities),
            "qualifications_valid": valid_q,
            "qualifications_expired": expired_q,
            "can_edit_content": self.has(CAP_CONTENT_EDITOR),
            "can_review_content": self.has(CAP_CONTENT_REVIEW),
            "can_publish_content": self.has(CAP_CONTENT_PUBLISH),
            "can_manage_profession": self.has(CAP_PROFESSION_ADMIN),
        }


def _qualification_valid(row: dict[str, Any]) -> bool:
    vu = row.get("valid_until")
    if vu is None or vu == "":
        return True
    if isinstance(vu, str):
        try:
            exp = date.fromisoformat(vu[:10])
        except ValueError:
            return False
    elif isinstance(vu, date):
        exp = vu
    else:
        return False
    return exp >= datetime.now(UTC).date()


def require_capability(policy: EffectiveProfessionPolicy, capability: str) -> None:
    if not policy.has(capability):
        raise HTTPException(status_code=403, detail=f"missing capability: {capability}")


def content_visible_to_policy(content: dict[str, Any], policy: EffectiveProfessionPolicy) -> bool:
    if str(content.get("status") or "") != "published":
        return False

    targets = [str(x).strip().lower() for x in (content.get("target_profession_roles") or []) if str(x).strip()]
    if targets:
        role = (policy.profession_role_slug or "").strip().lower()
        if not role or role not in targets:
            return False

    depts = [str(x).strip().lower() for x in (content.get("target_departments") or []) if str(x).strip()]
    if depts:
        dept = (policy.department_slug or "").strip().lower()
        if not dept or dept not in depts:
            return False

    required = [str(x).strip().lower() for x in (content.get("required_qualifications") or []) if str(x).strip()]
    if required:
        valid = {
            str(q.get("qualification_type") or "").strip().lower()
            for q in policy.qualifications
            if _qualification_valid(q)
        }
        if not all(r in valid for r in required):
            return False

    if policy.role_kind == "trainee":
        category = (content.get("content_category") or "").strip().lower()
        if category and policy.content_categories:
            allowed = {c.strip().lower() for c in policy.content_categories if str(c).strip()}
            if category not in allowed:
                return False

    return True
