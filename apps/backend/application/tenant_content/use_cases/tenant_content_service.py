"""Tenant CMS — validation, review workflow, and publish hooks (Tasks 04–06)."""

from __future__ import annotations

import difflib
import hashlib
import re
import unicodedata
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException

from apps.backend.application.rag.use_cases import rag_controller_services as rag_ctrl
from apps.backend.application.tenant_profession.use_cases.profession_policy_service import effective_policy
from apps.backend.domain.tenant_profession.policy import (
    CAP_CONTENT_EDITOR,
    CAP_CONTENT_PUBLISH,
    CAP_CONTENT_REVIEW,
    require_capability,
)
from apps.backend.infrastructure.db import db

rag_service = rag_ctrl.rag_service

TENANT_KNOWLEDGE_DOMAIN = "tenant_knowledge"
TENANT_KNOWLEDGE_DRAFT_DOMAIN = "tenant_knowledge_draft"
ALLOWED_SOURCE_TYPES = frozenset({"self_authored"})
ALLOWED_DISCLAIMER_LEVELS = frozenset({"learning_aid", "local_draft", "approved"})
ALLOWED_STATUSES = frozenset(
    {"draft", "in_review", "approved", "published", "deprecated", "archived"}
)
EDITABLE_STATUSES = frozenset({"draft", "published", "approved", "deprecated"})

_PHI_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bPatient\s+[A-ZÄÖÜ][a-zäöüß\-]+", re.I), "possible patient name"),
    (re.compile(r"\b(Fallnummer|Patienten-?ID|MRN)\s*[:#]?\s*\w*\d", re.I), "possible patient identifier"),
)


def content_sha256(body_md: str) -> str:
    return hashlib.sha256((body_md or "").encode("utf-8")).hexdigest()


def slugify_title(title: str) -> str:
    s = unicodedata.normalize("NFKD", title or "")
    s = s.encode("ascii", "ignore").decode("ascii")
    s = re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
    return (s[:120] or "note")


def unique_slug(tenant_id: int, base: str, *, exclude_id: uuid.UUID | None = None) -> str:
    slug = slugify_title(base)
    if not db.tenant_content_slug_exists(tenant_id, slug, exclude_id=exclude_id):
        return slug
    for i in range(2, 100):
        candidate = f"{slug}-{i}"[:128]
        if not db.tenant_content_slug_exists(tenant_id, candidate, exclude_id=exclude_id):
            return candidate
    raise HTTPException(status_code=409, detail="could not allocate unique slug")


def rag_source_uri(content_id: uuid.UUID | str) -> str:
    return f"tenant-content/{content_id}"


def phi_issues(body_md: str) -> list[str]:
    text = body_md or ""
    out: list[str] = []
    for pattern, label in _PHI_PATTERNS:
        if pattern.search(text):
            out.append(label)
    return out


def validate_body(body_md: str) -> str:
    body = (body_md or "").strip()
    if not body:
        raise HTTPException(status_code=400, detail="body_md is required")
    return body


def validate_source_type(source_type: str | None) -> str:
    st = (source_type or "self_authored").strip().lower()
    if st not in ALLOWED_SOURCE_TYPES:
        raise HTTPException(status_code=400, detail="source_type must be self_authored")
    return st


def validate_disclaimer_level(level: str | None) -> str:
    dl = (level or "learning_aid").strip().lower()
    if dl not in ALLOWED_DISCLAIMER_LEVELS:
        raise HTTPException(status_code=400, detail="invalid disclaimer_level")
    return dl


def _maybe_check_phi(body_md: str, vertical_profile: str | None) -> None:
    vp = (vertical_profile or "").strip().lower()
    if vp != "healthcare_ops":
        return
    issues = phi_issues(body_md)
    if issues:
        raise HTTPException(
            status_code=400,
            detail=f"content may contain patient identifiers ({', '.join(issues)}) — remove before publish",
        )


def _audit(
    *,
    content_id: uuid.UUID,
    tenant_id: int,
    event_type: str,
    actor_user_id: uuid.UUID,
    comment: str | None = None,
    content_version: int | None = None,
) -> None:
    db.tenant_content_audit_insert(
        content_id=content_id,
        tenant_id=tenant_id,
        event_type=event_type,
        actor_user_id=actor_user_id,
        comment=comment,
        content_version=content_version,
    )


def purge_rag_for_content(tenant_id: int, content_id: uuid.UUID, *, domain: str = TENANT_KNOWLEDGE_DOMAIN) -> int:
    return db.rag_delete_documents_by_source_uri(
        tenant_id,
        domain,
        rag_source_uri(content_id),
    )


def purge_all_rag_for_content(tenant_id: int, content_id: uuid.UUID) -> None:
    purge_rag_for_content(tenant_id, content_id, domain=TENANT_KNOWLEDGE_DOMAIN)
    purge_rag_for_content(tenant_id, content_id, domain=TENANT_KNOWLEDGE_DRAFT_DOMAIN)


def ingest_published_content(
    *,
    tenant_id: int,
    user_id: uuid.UUID,
    content_id: uuid.UUID,
    title: str,
    body_md: str,
) -> dict[str, Any]:
    purge_rag_for_content(tenant_id, content_id, domain=TENANT_KNOWLEDGE_DOMAIN)
    return rag_service.ingest_for_user(
        tenant_id,
        user_id,
        TENANT_KNOWLEDGE_DOMAIN,
        title,
        body_md,
        rag_source_uri(content_id),
    )


def ingest_draft_preview(
    *,
    tenant_id: int,
    user_id: uuid.UUID,
    content_id: uuid.UUID,
    title: str,
    body_md: str,
) -> dict[str, Any]:
    purge_rag_for_content(tenant_id, content_id, domain=TENANT_KNOWLEDGE_DRAFT_DOMAIN)
    return rag_service.ingest_for_user(
        tenant_id,
        user_id,
        TENANT_KNOWLEDGE_DRAFT_DOMAIN,
        title,
        body_md,
        rag_source_uri(content_id),
    )


def _snapshot_version(
    *,
    row: dict[str, Any],
    tenant_id: int,
    user_id: uuid.UUID,
    snapshot_reason: str = "publish",
) -> dict[str, Any]:
    return db.tenant_content_version_insert(
        content_id=uuid.UUID(str(row["id"])),
        tenant_id=tenant_id,
        version=int(row.get("version") or 1),
        title=str(row.get("title") or ""),
        body_md=str(row.get("body_md") or ""),
        content_sha256=str(row.get("content_sha256") or ""),
        created_by_user_id=user_id,
        snapshot_reason=snapshot_reason,
    )


def create_draft(
    *,
    tenant_id: int,
    user_id: uuid.UUID,
    title: str,
    body_md: str,
    slug: str | None = None,
    disclaimer_level: str | None = None,
    vertical_profile: str | None = None,
    source_type: str | None = None,
    target_profession_roles: list[str] | None = None,
    target_departments: list[str] | None = None,
    required_qualifications: list[str] | None = None,
    content_category: str | None = None,
) -> dict[str, Any]:
    policy = effective_policy(user_id, tenant_id)
    require_capability(policy, CAP_CONTENT_EDITOR)
    body = validate_body(body_md)
    st = validate_source_type(source_type)
    dl = validate_disclaimer_level(disclaimer_level)
    slug_final = unique_slug(tenant_id, slug or title)
    return db.tenant_content_insert(
        tenant_id=tenant_id,
        slug=slug_final,
        title=(title or "").strip() or "Untitled",
        body_md=body,
        content_sha256=content_sha256(body),
        author_user_id=user_id,
        source_type=st,
        disclaimer_level=dl,
        vertical_profile=vertical_profile,
        target_profession_roles=target_profession_roles,
        target_departments=target_departments,
        required_qualifications=required_qualifications,
        content_category=content_category,
    )


def update_content(
    *,
    tenant_id: int,
    content_id: uuid.UUID,
    user_id: uuid.UUID,
    title: str | None = None,
    body_md: str | None = None,
    slug: str | None = None,
    disclaimer_level: str | None = None,
    vertical_profile: str | None = None,
    target_profession_roles: list[str] | None = None,
    target_departments: list[str] | None = None,
    required_qualifications: list[str] | None = None,
    content_category: str | None = None,
) -> dict[str, Any]:
    policy = effective_policy(user_id, tenant_id)
    require_capability(policy, CAP_CONTENT_EDITOR)
    row = db.tenant_content_get(content_id, tenant_id)
    if not row:
        raise HTTPException(status_code=404, detail="content not found")
    status = str(row.get("status") or "draft")
    if status == "archived":
        raise HTTPException(status_code=409, detail="archived content cannot be edited")
    if status == "in_review":
        raise HTTPException(status_code=409, detail="content in review — wait for reviewer or recall first")

    new_body = validate_body(body_md) if body_md is not None else row["body_md"]
    new_sha = content_sha256(new_body)
    new_title = (title.strip() if title is not None else row["title"]) or "Untitled"
    new_slug = str(row.get("slug") or "")
    if slug is not None:
        new_slug = unique_slug(tenant_id, slug, exclude_id=content_id)

    new_status = status
    clear_published = False
    clear_approved = False
    body_changed = new_sha != row.get("content_sha256")
    if status in ("published", "approved", "deprecated") and body_changed:
        new_status = "draft"
        clear_published = status == "published"
        clear_approved = status in ("approved", "deprecated")
        purge_all_rag_for_content(tenant_id, content_id)

    updated = db.tenant_content_update(
        content_id,
        tenant_id,
        slug=new_slug,
        title=new_title,
        body_md=new_body,
        content_sha256=new_sha,
        status=new_status,
        disclaimer_level=validate_disclaimer_level(disclaimer_level)
        if disclaimer_level is not None
        else None,
        vertical_profile=vertical_profile,
        target_profession_roles=target_profession_roles,
        target_departments=target_departments,
        required_qualifications=required_qualifications,
        content_category=content_category,
        clear_published_at=clear_published,
        clear_approved=clear_approved,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="content not found")
    return updated


def submit_for_review(
    *,
    tenant_id: int,
    user_id: uuid.UUID,
    content_id: uuid.UUID,
) -> dict[str, Any]:
    policy = effective_policy(user_id, tenant_id)
    require_capability(policy, CAP_CONTENT_EDITOR)
    row = db.tenant_content_get(content_id, tenant_id)
    if not row:
        raise HTTPException(status_code=404, detail="content not found")
    if str(row.get("status") or "") != "draft":
        raise HTTPException(status_code=409, detail="only drafts can be submitted for review")

    body = validate_body(str(row.get("body_md") or ""))
    updated = db.tenant_content_update(content_id, tenant_id, status="in_review", clear_approved=True)
    if not updated:
        raise HTTPException(status_code=404, detail="content not found")

    draft_rag = ingest_draft_preview(
        tenant_id=tenant_id,
        user_id=user_id,
        content_id=content_id,
        title=str(updated.get("title") or ""),
        body_md=body,
    )
    _audit(
        content_id=content_id,
        tenant_id=tenant_id,
        event_type="submit",
        actor_user_id=user_id,
        content_version=int(updated.get("version") or 1),
    )
    return {"content": updated, "draft_rag": draft_rag}


def approve_content(
    *,
    tenant_id: int,
    user_id: uuid.UUID,
    content_id: uuid.UUID,
) -> dict[str, Any]:
    policy = effective_policy(user_id, tenant_id)
    require_capability(policy, CAP_CONTENT_REVIEW)
    row = db.tenant_content_get(content_id, tenant_id)
    if not row:
        raise HTTPException(status_code=404, detail="content not found")
    if str(row.get("status") or "") != "in_review":
        raise HTTPException(status_code=409, detail="only in_review content can be approved")

    now = datetime.now(UTC)
    updated = db.tenant_content_update(
        content_id,
        tenant_id,
        status="approved",
        approved_at=now,
        approved_by_user_id=user_id,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="content not found")
    _audit(
        content_id=content_id,
        tenant_id=tenant_id,
        event_type="approve",
        actor_user_id=user_id,
        content_version=int(updated.get("version") or 1),
    )
    return updated


def reject_content(
    *,
    tenant_id: int,
    user_id: uuid.UUID,
    content_id: uuid.UUID,
    comment: str,
) -> dict[str, Any]:
    policy = effective_policy(user_id, tenant_id)
    require_capability(policy, CAP_CONTENT_REVIEW)
    note = (comment or "").strip()
    if not note:
        raise HTTPException(status_code=400, detail="rejection comment is required")
    row = db.tenant_content_get(content_id, tenant_id)
    if not row:
        raise HTTPException(status_code=404, detail="content not found")
    if str(row.get("status") or "") != "in_review":
        raise HTTPException(status_code=409, detail="only in_review content can be rejected")

    purge_rag_for_content(tenant_id, content_id, domain=TENANT_KNOWLEDGE_DRAFT_DOMAIN)
    updated = db.tenant_content_update(
        content_id,
        tenant_id,
        status="draft",
        last_review_comment=note,
        clear_approved=True,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="content not found")
    _audit(
        content_id=content_id,
        tenant_id=tenant_id,
        event_type="reject",
        actor_user_id=user_id,
        comment=note,
        content_version=int(updated.get("version") or 1),
    )
    return updated


def publish_content(
    *,
    tenant_id: int,
    user_id: uuid.UUID,
    content_id: uuid.UUID,
    override: bool = False,
) -> dict[str, Any]:
    policy = effective_policy(user_id, tenant_id)
    require_capability(policy, CAP_CONTENT_PUBLISH)
    row = db.tenant_content_get(content_id, tenant_id)
    if not row:
        raise HTTPException(status_code=404, detail="content not found")
    status = str(row.get("status") or "")
    if status == "archived":
        raise HTTPException(status_code=409, detail="archived content cannot be published")
    if status not in ("approved", "published"):
        if override and policy.is_tenant_admin:
            _audit(
                content_id=content_id,
                tenant_id=tenant_id,
                event_type="admin_override",
                actor_user_id=user_id,
                content_version=int(row.get("version") or 1),
            )
        else:
            raise HTTPException(status_code=409, detail="content must be approved before publish")

    body = validate_body(str(row.get("body_md") or ""))
    validate_source_type(str(row.get("source_type") or "self_authored"))
    _maybe_check_phi(body, row.get("vertical_profile"))

    new_sha = content_sha256(body)
    version = int(row.get("version") or 1)
    body_changed = new_sha != row.get("content_sha256")
    if body_changed:
        version += 1

    if status == "approved" or (status == "published" and body_changed):
        _snapshot_version(
            row={**row, "version": version, "body_md": body, "content_sha256": new_sha},
            tenant_id=tenant_id,
            user_id=user_id,
        )

    now = datetime.now(UTC)
    updated = db.tenant_content_update(
        content_id,
        tenant_id,
        content_sha256=new_sha,
        status="published",
        version=version,
        published_at=now,
        published_by_user_id=user_id,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="content not found")

    purge_rag_for_content(tenant_id, content_id, domain=TENANT_KNOWLEDGE_DRAFT_DOMAIN)
    ingest_out = ingest_published_content(
        tenant_id=tenant_id,
        user_id=user_id,
        content_id=content_id,
        title=str(updated.get("title") or ""),
        body_md=body,
    )
    _audit(
        content_id=content_id,
        tenant_id=tenant_id,
        event_type="publish",
        actor_user_id=user_id,
        content_version=version,
    )
    return {"content": updated, "rag": ingest_out}


def archive_content(*, tenant_id: int, user_id: uuid.UUID, content_id: uuid.UUID) -> dict[str, Any]:
    policy = effective_policy(user_id, tenant_id)
    require_capability(policy, CAP_CONTENT_PUBLISH)
    row = db.tenant_content_get(content_id, tenant_id)
    if not row:
        raise HTTPException(status_code=404, detail="content not found")

    purge_all_rag_for_content(tenant_id, content_id)
    updated = db.tenant_content_update(
        content_id,
        tenant_id,
        status="archived",
        clear_published_at=True,
        clear_approved=True,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="content not found")
    _audit(
        content_id=content_id,
        tenant_id=tenant_id,
        event_type="archive",
        actor_user_id=user_id,
        content_version=int(updated.get("version") or 1),
    )
    return updated


def list_versions(*, tenant_id: int, content_id: uuid.UUID, user_id: uuid.UUID) -> list[dict[str, Any]]:
    policy = effective_policy(user_id, tenant_id)
    require_capability(policy, CAP_CONTENT_EDITOR)
    row = db.tenant_content_get(content_id, tenant_id)
    if not row:
        raise HTTPException(status_code=404, detail="content not found")
    return db.tenant_content_versions_list(content_id, tenant_id)


def version_diff(
    *,
    tenant_id: int,
    content_id: uuid.UUID,
    user_id: uuid.UUID,
    from_version: int,
    to_version: int,
) -> dict[str, Any]:
    policy = effective_policy(user_id, tenant_id)
    require_capability(policy, CAP_CONTENT_EDITOR)
    row = db.tenant_content_get(content_id, tenant_id)
    if not row:
        raise HTTPException(status_code=404, detail="content not found")
    left = db.tenant_content_version_get(content_id, tenant_id, from_version)
    right = db.tenant_content_version_get(content_id, tenant_id, to_version)
    if not left or not right:
        raise HTTPException(status_code=404, detail="version not found")
    diff_lines = list(
        difflib.unified_diff(
            str(left.get("body_md") or "").splitlines(),
            str(right.get("body_md") or "").splitlines(),
            fromfile=f"v{from_version}",
            tofile=f"v{to_version}",
            lineterm="",
        )
    )
    return {
        "from_version": from_version,
        "to_version": to_version,
        "diff": "\n".join(diff_lines),
    }


def list_audit_events(*, tenant_id: int, content_id: uuid.UUID, user_id: uuid.UUID) -> list[dict[str, Any]]:
    policy = effective_policy(user_id, tenant_id)
    require_capability(policy, CAP_CONTENT_EDITOR)
    row = db.tenant_content_get(content_id, tenant_id)
    if not row:
        raise HTTPException(status_code=404, detail="content not found")
    return db.tenant_content_audit_list(content_id, tenant_id)
