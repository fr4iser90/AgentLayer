"""Profession RBAC policy (Task 05)."""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from unittest.mock import patch

from apps.backend.application.tenant_profession.use_cases import profession_policy_service as prof_svc
from apps.backend.application.tenant_profession.use_cases.profession_policy_service import effective_policy
from apps.backend.domain.tenant_profession.policy import EffectiveProfessionPolicy, content_visible_to_policy


def _policy(**kwargs) -> EffectiveProfessionPolicy:
    defaults = dict(
        tenant_id=1,
        user_id=uuid.uuid4(),
        is_tenant_admin=False,
        profession_role_slug="anesthesia_nurse",
        profession_role_name="Anesthesia nurse",
        role_kind="end_user",
        department_slug="anesthesia",
        department_name="Anesthesia",
        content_categories=(),
        capabilities=frozenset({"knowledge.search"}),
        qualifications=(),
    )
    defaults.update(kwargs)
    return EffectiveProfessionPolicy(**defaults)


def test_content_hidden_for_wrong_profession_role() -> None:
    content = {
        "status": "published",
        "target_profession_roles": ["ota"],
        "target_departments": [],
        "required_qualifications": [],
    }
    policy = _policy(profession_role_slug="anesthesia_nurse")
    assert content_visible_to_policy(content, policy) is False


def test_content_visible_for_matching_role() -> None:
    content = {
        "status": "published",
        "target_profession_roles": ["anesthesia_nurse"],
        "target_departments": [],
        "required_qualifications": [],
    }
    policy = _policy(profession_role_slug="anesthesia_nurse")
    assert content_visible_to_policy(content, policy) is True


def test_expired_qualification_blocks_content() -> None:
    content = {
        "status": "published",
        "target_profession_roles": [],
        "target_departments": [],
        "required_qualifications": ["basic_life_support"],
    }
    policy = _policy(
        qualifications=(
            {
                "qualification_type": "basic_life_support",
                "valid_until": (date.today() - timedelta(days=1)).isoformat(),
            },
        )
    )
    assert content_visible_to_policy(content, policy) is False


def test_trainee_limited_to_onboarding_category() -> None:
    content = {
        "status": "published",
        "target_profession_roles": [],
        "target_departments": [],
        "required_qualifications": [],
        "content_category": "advanced",
    }
    policy = _policy(role_kind="trainee", content_categories=("onboarding",))
    assert content_visible_to_policy(content, policy) is False

    onboarding = {**content, "content_category": "onboarding"}
    assert content_visible_to_policy(onboarding, policy) is True


def test_filter_rag_hits_strips_restricted_cms_chunks() -> None:
    policy = _policy(profession_role_slug="anesthesia_nurse")
    hits = [
        {"source_uri": "tenant-content/550e8400-e29b-41d4-a716-446655440000", "title": "OTA note"},
        {"source_uri": "legacy-direct", "title": "open"},
    ]
    cms_row = {
        "status": "published",
        "target_profession_roles": ["ota"],
        "target_departments": [],
        "required_qualifications": [],
    }
    with patch(
        "apps.backend.application.tenant_profession.use_cases.profession_policy_service.tenant_content_get_by_source_uri",
        return_value=cms_row,
    ):
        out = prof_svc.filter_rag_hits(hits, policy)
    assert len(out) == 1
    assert out[0]["source_uri"] == "legacy-direct"


def test_content_reviewer_capability() -> None:
    uid = uuid.uuid4()
    with (
        patch("apps.backend.application.tenant_profession.use_cases.profession_policy_service.db.user_is_tenant_admin", return_value=False),
        patch("apps.backend.application.tenant_profession.use_cases.profession_policy_service.db.user_site_role", return_value="site_user"),
        patch("apps.backend.application.tenant_profession.use_cases.profession_policy_service.db.profession_roles_count", return_value=1),
        patch(
            "apps.backend.application.tenant_profession.use_cases.profession_policy_service.db.profession_assignment_get",
            return_value={
                "profession_role_slug": "content_reviewer",
                "profession_role_name": "Reviewer",
                "role_kind": "content_reviewer",
                "content_categories": [],
            },
        ),
        patch("apps.backend.application.tenant_profession.use_cases.profession_policy_service.db.qualifications_list", return_value=[]),
    ):
        pol = effective_policy(uid, 1)
    assert pol.has("content.review")
    assert not pol.has("content.publish")


def test_content_editor_capability() -> None:
    uid = uuid.uuid4()
    with (
        patch("apps.backend.application.tenant_profession.use_cases.profession_policy_service.db.user_is_tenant_admin", return_value=False),
        patch("apps.backend.application.tenant_profession.use_cases.profession_policy_service.db.user_site_role", return_value="site_user"),
        patch("apps.backend.application.tenant_profession.use_cases.profession_policy_service.db.profession_roles_count", return_value=1),
        patch(
            "apps.backend.application.tenant_profession.use_cases.profession_policy_service.db.profession_assignment_get",
            return_value={
                "profession_role_slug": "content_editor",
                "profession_role_name": "Editor",
                "role_kind": "content_editor",
                "content_categories": [],
            },
        ),
        patch("apps.backend.application.tenant_profession.use_cases.profession_policy_service.db.qualifications_list", return_value=[]),
    ):
        pol = effective_policy(uid, 1)
    assert pol.has("content.editor")
    assert not pol.has("content.publish")
