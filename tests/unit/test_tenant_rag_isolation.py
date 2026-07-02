"""Tenant-wide RAG domain isolation (Task 03)."""

from __future__ import annotations

import uuid
from unittest.mock import patch

from apps.backend.infrastructure.rag import rag_core


from apps.backend.domain.tenant_profession.policy import EffectiveProfessionPolicy

_FAKE_POLICY = EffectiveProfessionPolicy(
    tenant_id=1,
    user_id=uuid.uuid4(),
    is_tenant_admin=False,
    profession_role_slug="anesthesia_nurse",
    profession_role_name="Nurse",
    role_kind="end_user",
    department_slug=None,
    department_name=None,
    content_categories=(),
    capabilities=frozenset({"knowledge.search"}),
    qualifications=(),
)


def test_search_for_identity_uses_tenant_wide_for_tenant_knowledge() -> None:
    tenant_id = 1
    user_id = uuid.uuid4()
    fake_hits = [{"document_id": 42, "title": "probe", "content": "x"}]

    with (
        patch.object(rag_core.operator_settings, "rag_settings", return_value={"enabled": True, "top_k": 5}),
        patch.object(
            rag_core.operator_settings,
            "effective_rag_tenant_shared_domains",
            return_value=["tenant_knowledge", "agentlayer_docs"],
        ),
        patch.object(rag_core, "embed_one", return_value=[0.1, 0.2]),
        patch.object(rag_core, "get_identity", return_value=(tenant_id, user_id)),
        patch.object(rag_core.db, "rag_vector_search", return_value=fake_hits) as mock_search,
        patch(
            "apps.backend.application.tenant_profession.use_cases.profession_policy_service.effective_policy",
            return_value=_FAKE_POLICY,
        ),
        patch(
            "apps.backend.application.tenant_profession.use_cases.profession_policy_service.filter_rag_hits",
            side_effect=lambda hits, _policy: hits,
        ),
    ):
        out = rag_core.search_for_identity("Beatmungsschlauch", domain="tenant_knowledge", limit=3)

    assert out == fake_hits
    mock_search.assert_called_once()
    _args, kwargs = mock_search.call_args
    assert _args[0] == tenant_id
    assert _args[1] == user_id
    assert kwargs.get("tenant_wide_domain") is True


def test_search_for_identity_personal_domain_not_tenant_wide() -> None:
    tenant_id = 1
    user_id = uuid.uuid4()

    with (
        patch.object(rag_core.operator_settings, "rag_settings", return_value={"enabled": True, "top_k": 5}),
        patch.object(
            rag_core.operator_settings,
            "effective_rag_tenant_shared_domains",
            return_value=["tenant_knowledge"],
        ),
        patch.object(rag_core, "embed_one", return_value=[0.1]),
        patch.object(rag_core, "get_identity", return_value=(tenant_id, user_id)),
        patch.object(rag_core.db, "rag_vector_search", return_value=[]) as mock_search,
    ):
        rag_core.search_for_identity("notes", domain="personal_notes", limit=5)

    _args, kwargs = mock_search.call_args
    assert kwargs.get("tenant_wide_domain") is False
