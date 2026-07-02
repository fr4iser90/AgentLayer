"""Tenant CMS review workflow (Task 06)."""

from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from apps.backend.application.tenant_content.use_cases import tenant_content_service as cms
from apps.backend.domain.tenant_profession.policy import (
    CAP_CONTENT_EDITOR,
    CAP_CONTENT_PUBLISH,
    CAP_CONTENT_REVIEW,
    EffectiveProfessionPolicy,
)

_EDITOR = EffectiveProfessionPolicy(
    tenant_id=1,
    user_id=uuid.uuid4(),
    is_tenant_admin=False,
    profession_role_slug="content_editor",
    profession_role_name="Editor",
    role_kind="content_editor",
    department_slug=None,
    department_name=None,
    content_categories=(),
    capabilities=frozenset({CAP_CONTENT_EDITOR}),
    qualifications=(),
)

_REVIEWER = EffectiveProfessionPolicy(
    tenant_id=1,
    user_id=uuid.uuid4(),
    is_tenant_admin=False,
    profession_role_slug="content_reviewer",
    profession_role_name="Reviewer",
    role_kind="content_reviewer",
    department_slug=None,
    department_name=None,
    content_categories=(),
    capabilities=frozenset({CAP_CONTENT_EDITOR, CAP_CONTENT_REVIEW}),
    qualifications=(),
)

_APPROVER = EffectiveProfessionPolicy(
    tenant_id=1,
    user_id=uuid.uuid4(),
    is_tenant_admin=False,
    profession_role_slug="content_approver",
    profession_role_name="Approver",
    role_kind="content_approver",
    department_slug=None,
    department_name=None,
    content_categories=(),
    capabilities=frozenset({CAP_CONTENT_EDITOR, CAP_CONTENT_PUBLISH}),
    qualifications=(),
)


def _row(**kwargs) -> dict:
    defaults = {
        "id": str(uuid.uuid4()),
        "title": "Checklist",
        "body_md": "body text",
        "content_sha256": cms.content_sha256("body text"),
        "status": "draft",
        "version": 1,
        "source_type": "self_authored",
        "vertical_profile": "default_ops",
    }
    defaults.update(kwargs)
    return defaults


def test_editor_cannot_publish_draft_directly() -> None:
    cid = uuid.uuid4()
    row = _row(id=str(cid), status="draft")
    with (
        patch.object(cms, "effective_policy", return_value=_APPROVER),
        patch.object(cms.db, "tenant_content_get", return_value=row),
    ):
        with pytest.raises(HTTPException) as exc:
            cms.publish_content(tenant_id=1, user_id=uuid.uuid4(), content_id=cid)
    assert exc.value.status_code == 409


def test_submit_moves_to_in_review_and_ingests_draft_rag() -> None:
    cid = uuid.uuid4()
    row = _row(id=str(cid), status="draft")
    updated = {**row, "status": "in_review"}
    with (
        patch.object(cms, "effective_policy", return_value=_EDITOR),
        patch.object(cms.db, "tenant_content_get", return_value=row),
        patch.object(cms.db, "tenant_content_update", return_value=updated),
        patch.object(cms, "ingest_draft_preview", return_value={"chunk_count": 1}) as ingest,
        patch.object(cms.db, "tenant_content_audit_insert") as audit,
    ):
        out = cms.submit_for_review(tenant_id=1, user_id=uuid.uuid4(), content_id=cid)
    assert out["content"]["status"] == "in_review"
    ingest.assert_called_once()
    audit.assert_called_once()


def test_reviewer_rejects_with_comment() -> None:
    cid = uuid.uuid4()
    row = _row(id=str(cid), status="in_review")
    updated = {**row, "status": "draft", "last_review_comment": "fix typos"}
    with (
        patch.object(cms, "effective_policy", return_value=_REVIEWER),
        patch.object(cms.db, "tenant_content_get", return_value=row),
        patch.object(cms, "purge_rag_for_content", return_value=1),
        patch.object(cms.db, "tenant_content_update", return_value=updated),
        patch.object(cms.db, "tenant_content_audit_insert") as audit,
    ):
        out = cms.reject_content(
            tenant_id=1,
            user_id=uuid.uuid4(),
            content_id=cid,
            comment="fix typos",
        )
    assert out["status"] == "draft"
    audit.assert_called_once()


def test_reject_requires_comment() -> None:
    cid = uuid.uuid4()
    row = _row(id=str(cid), status="in_review")
    with (
        patch.object(cms, "effective_policy", return_value=_REVIEWER),
        patch.object(cms.db, "tenant_content_get", return_value=row),
    ):
        with pytest.raises(HTTPException) as exc:
            cms.reject_content(tenant_id=1, user_id=uuid.uuid4(), content_id=cid, comment="  ")
    assert exc.value.status_code == 400


def test_publish_from_approved_ingests_production_rag_only() -> None:
    cid = uuid.uuid4()
    row = _row(id=str(cid), status="approved")
    published = {**row, "status": "published", "version": 1}
    with (
        patch.object(cms, "effective_policy", return_value=_APPROVER),
        patch.object(cms.db, "tenant_content_get", return_value=row),
        patch.object(cms, "_snapshot_version") as snap,
        patch.object(cms.db, "tenant_content_update", return_value=published),
        patch.object(cms, "purge_rag_for_content", return_value=0),
        patch.object(cms, "ingest_published_content", return_value={"chunk_count": 2}) as ingest,
        patch.object(cms.db, "tenant_content_audit_insert") as audit,
    ):
        out = cms.publish_content(tenant_id=1, user_id=uuid.uuid4(), content_id=cid)
    snap.assert_called_once()
    ingest.assert_called_once()
    audit.assert_called_once()
    assert out["content"]["status"] == "published"


def test_update_blocked_while_in_review() -> None:
    cid = uuid.uuid4()
    row = _row(id=str(cid), status="in_review")
    with (
        patch.object(cms, "effective_policy", return_value=_EDITOR),
        patch.object(cms.db, "tenant_content_get", return_value=row),
    ):
        with pytest.raises(HTTPException) as exc:
            cms.update_content(
                tenant_id=1,
                content_id=cid,
                user_id=uuid.uuid4(),
                body_md="changed",
            )
    assert exc.value.status_code == 409
