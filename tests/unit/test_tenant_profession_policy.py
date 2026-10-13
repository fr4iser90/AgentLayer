"""Profession RBAC policy (Task 05)."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import patch

from apps.backend.application.tenant_profession.use_cases import profession_policy_service as prof_svc
from apps.backend.application.tenant_profession.use_cases.profession_policy_service import effective_policy
from apps.backend.infrastructure.db.tenant_profession_persistence import profession_role_insert
from apps.backend.domain.tenant_profession.policy import (
    EffectiveProfessionPolicy,
    content_in_write_scope,
    content_visible_to_policy,
)


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
                # UTC, matching _qualification_valid — a local "yesterday" is still today
                # in UTC for negative offsets and late evenings east of Greenwich.
                "valid_until": (datetime.now(UTC).date() - timedelta(days=1)).isoformat(),
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


def test_scoped_moderator_write_scope_by_category() -> None:
    """content_reviewer with content_categories may only touch matching notes."""
    policy = _policy(
        role_kind="content_reviewer",
        profession_role_slug="hygiene_moderator",
        content_categories=("hygiene",),
        capabilities=frozenset({"knowledge.search", "content.editor", "content.review"}),
    )
    assert content_in_write_scope(policy, content_category="hygiene") is True
    assert content_in_write_scope(policy, content_category="abx") is False
    assert content_in_write_scope(policy, content_category=None) is False
    # Empty categories on role = unrestricted (global editor)
    open_editor = _policy(
        role_kind="content_editor",
        content_categories=(),
        capabilities=frozenset({"knowledge.search", "content.editor"}),
    )
    assert content_in_write_scope(open_editor, content_category="abx") is True
    assert content_in_write_scope(open_editor, content_category=None) is True


def test_scoped_moderator_department_gate() -> None:
    policy = _policy(
        role_kind="content_reviewer",
        department_slug="or",
        content_categories=("peri_op",),
        capabilities=frozenset({"knowledge.search", "content.editor", "content.review"}),
    )
    assert (
        content_in_write_scope(
            policy,
            content_category="peri_op",
            target_departments=["or"],
        )
        is True
    )
    assert (
        content_in_write_scope(
            policy,
            content_category="peri_op",
            target_departments=["anesthesia"],
        )
        is False
    )


def test_tenant_admin_bypasses_write_scope() -> None:
    policy = _policy(
        is_tenant_admin=True,
        content_categories=("hygiene",),
        capabilities=frozenset({"knowledge.search", "content.editor", "content.review", "content.publish", "profession.admin"}),
    )
    assert content_in_write_scope(policy, content_category="abx") is True


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
            "apps.backend.application.tenant_profession.use_cases.profession_policy_service.db.profession_assignments_list_user",
            return_value=[
                {
                    "profession_role_slug": "content_reviewer",
                    "profession_role_name": "Reviewer",
                    "role_kind": "content_reviewer",
                    "content_categories": [],
                    "capabilities": [
                        "knowledge.search",
                        "content.editor",
                        "content.review",
                    ],
                },
            ],
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
            "apps.backend.application.tenant_profession.use_cases.profession_policy_service.db.profession_assignments_list_user",
            return_value=[
                {
                    "profession_role_slug": "content_editor",
                    "profession_role_name": "Editor",
                    "role_kind": "content_editor",
                    "content_categories": [],
                    "capabilities": [
                        "knowledge.search",
                        "content.editor",
                    ],
                },
            ],
        ),
        patch("apps.backend.application.tenant_profession.use_cases.profession_policy_service.db.qualifications_list", return_value=[]),
    ):
        pol = effective_policy(uid, 1)
    assert pol.has("content.editor")
    assert not pol.has("content.publish")


def test_profession_role_insert_caps_are_json_serializable() -> None:
    """``capabilities_for_role_kind`` returns a frozenset; the JSONB column needs a list.

    A frozenset reaching the driver raised
    ``TypeError: Object of type frozenset is not JSON serializable`` inside
    ``ensure_tenant_profession_defaults``, which ``/auth/me`` calls — so the first
    non-admin user on a tenant with no profession roles crashed the endpoint.
    """
    captured: dict[str, Any] = {}

    class _Cur:
        def execute(self, _sql, params=None):
            captured["params"] = params
            return None

        def fetchone(self):
            return {
                "id": uuid.uuid4(),
                "tenant_id": 1,
                "slug": "nurse",
                "name": "Nurse",
                "role_kind": "end_user",
                "content_categories": [],
                "capabilities": [],
                "created_at": None,
            }

        def __enter__(self):
            return self

        def __exit__(self, *_a):
            return False

    class _Conn:
        def cursor(self, **_kw):
            return _Cur()

        def commit(self):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_a):
            return False

    class _Pool:
        def connection(self):
            return _Conn()

    with patch(
        "apps.backend.infrastructure.db.tenant_profession_persistence.pool",
        return_value=_Pool(),
    ):
        profession_role_insert(1, "nurse", "Nurse", "end_user")

    caps = captured["params"][-1]
    assert isinstance(getattr(caps, "obj", caps), list), (
        f"capabilities must reach the driver as a list, got {type(caps).__name__}"
    )
    json.dumps(getattr(caps, "obj", caps))
