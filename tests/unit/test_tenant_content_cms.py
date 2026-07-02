"""Tenant CMS service (Task 04)."""

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

_ADMIN_POLICY = EffectiveProfessionPolicy(
    tenant_id=1,
    user_id=uuid.uuid4(),
    is_tenant_admin=True,
    profession_role_slug=None,
    profession_role_name=None,
    role_kind="domain_admin",
    department_slug=None,
    department_name=None,
    content_categories=(),
    capabilities=frozenset({CAP_CONTENT_EDITOR, CAP_CONTENT_REVIEW, CAP_CONTENT_PUBLISH}),
    qualifications=(),
)


def test_slugify_title() -> None:
    assert cms.slugify_title("OP-Vorbereitung Checkliste") == "op-vorbereitung-checkliste"


def test_phi_issues_detects_patient_name() -> None:
    issues = cms.phi_issues("Bei Patient Müller vorsichtig sein.")
    assert any("patient" in i.lower() for i in issues)


def test_validate_body_rejects_empty() -> None:
    with pytest.raises(HTTPException) as exc:
        cms.validate_body("   ")
    assert exc.value.status_code == 400


def test_publish_increments_version_on_body_change() -> None:
    cid = uuid.uuid4()
    row = {
        "id": str(cid),
        "title": "Checklist",
        "body_md": "old body",
        "content_sha256": cms.content_sha256("old body"),
        "status": "approved",
        "version": 1,
        "source_type": "self_authored",
        "vertical_profile": "default_ops",
    }

    with (
        patch.object(cms, "effective_policy", return_value=_ADMIN_POLICY),
        patch.object(cms.db, "tenant_content_get", return_value=row),
        patch.object(cms, "_snapshot_version"),
        patch.object(cms.db, "tenant_content_update", return_value={**row, "version": 2, "status": "published"}) as upd,
        patch.object(cms, "purge_rag_for_content", return_value=0),
        patch.object(cms, "ingest_published_content", return_value={"ok": True, "chunk_count": 2}) as ingest,
        patch.object(cms.db, "tenant_content_audit_insert"),
    ):
        out = cms.publish_content(tenant_id=1, user_id=uuid.uuid4(), content_id=cid)

    assert out["content"]["status"] == "published"
    upd.assert_called_once()
    ingest.assert_called_once()


def test_publish_rejects_phi_for_healthcare_ops() -> None:
    cid = uuid.uuid4()
    row = {
        "id": str(cid),
        "title": "Note",
        "body_md": "Patient Schmidt hat Allergien.",
        "content_sha256": cms.content_sha256("x"),
        "status": "approved",
        "version": 1,
        "source_type": "self_authored",
        "vertical_profile": "healthcare_ops",
    }
    with (
        patch.object(cms, "effective_policy", return_value=_ADMIN_POLICY),
        patch.object(cms.db, "tenant_content_get", return_value=row),
    ):
        with pytest.raises(HTTPException) as exc:
            cms.publish_content(tenant_id=1, user_id=uuid.uuid4(), content_id=cid)
    assert exc.value.status_code == 400


def test_update_published_body_demotes_to_draft_and_purges_rag() -> None:
    cid = uuid.uuid4()
    row = {
        "id": str(cid),
        "slug": "note",
        "title": "Note",
        "body_md": "published text",
        "content_sha256": cms.content_sha256("published text"),
        "status": "published",
        "version": 1,
    }
    with (
        patch.object(cms, "effective_policy", return_value=_ADMIN_POLICY),
        patch.object(cms.db, "tenant_content_get", return_value=row),
        patch.object(cms, "purge_all_rag_for_content") as purge,
        patch.object(cms.db, "tenant_content_update", return_value={**row, "status": "draft"}) as upd,
    ):
        out = cms.update_content(
            tenant_id=1, content_id=cid, user_id=uuid.uuid4(), body_md="new draft text"
        )

    purge.assert_called_once()
    upd.assert_called_once()
    assert out["status"] == "draft"


def test_archive_purges_rag() -> None:
    cid = uuid.uuid4()
    row = {"id": str(cid), "status": "published", "body_md": "x", "content_sha256": "y", "version": 1}
    with (
        patch.object(cms, "effective_policy", return_value=_ADMIN_POLICY),
        patch.object(cms.db, "tenant_content_get", return_value=row),
        patch.object(cms, "purge_all_rag_for_content") as purge,
        patch.object(cms.db, "tenant_content_update", return_value={**row, "status": "archived"}) as upd,
        patch.object(cms.db, "tenant_content_audit_insert"),
    ):
        out = cms.archive_content(tenant_id=1, user_id=uuid.uuid4(), content_id=cid)

    purge.assert_called_once()
    upd.assert_called_once()
    assert out["status"] == "archived"
