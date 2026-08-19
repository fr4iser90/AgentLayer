"""Tenant CMS helpers — validation, RAG hooks, audit, write-scope checks."""

from __future__ import annotations

import hashlib
import re
import unicodedata
import uuid
from typing import Any

from fastapi import HTTPException

from apps.backend.application.rag.use_cases import rag_controller_services as rag_ctrl
from apps.backend.domain.tenant_profession.policy import (
    EffectiveProfessionPolicy,
    require_content_in_write_scope,
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


def row_target_departments(row: dict[str, Any] | None) -> list[str]:
    if not row:
        return []
    raw = row.get("target_departments") or []
    if not isinstance(raw, list):
        return []
    return [str(x) for x in raw]


def assert_write_scope(
    policy: EffectiveProfessionPolicy,
    *,
    content_category: str | None,
    target_departments: list[str] | None,
) -> None:
    require_content_in_write_scope(
        policy,
        content_category=content_category,
        target_departments=target_departments,
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


def maybe_check_phi(body_md: str, vertical_profile: str | None) -> None:
    vp = (vertical_profile or "").strip().lower()
    if vp != "healthcare_ops":
        return
    issues = phi_issues(body_md)
    if issues:
        raise HTTPException(
            status_code=400,
            detail=f"content may contain patient identifiers ({', '.join(issues)}) — remove before publish",
        )


def audit_content_event(
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


def snapshot_version(
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
