"""Org surface guards — admin vs tenant CMS in multi_tenant mode.

Patched at ``has_org_surface`` rather than ``deployment_mode`` because that is
what the guards now ask. Patching the raw mode would leave the new indirection
untested and would silently pass for a mode nobody considered.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from apps.backend.application.org.use_cases import org_surface_guard as guard


def test_admin_cms_allowed_in_agent_system() -> None:
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(guard.operator_settings, "has_org_surface", lambda: False)
        guard.reject_admin_tenant_content_in_multi_tenant()


def test_admin_cms_allowed_in_single_user() -> None:
    """No org surface exists, so the platform admin CMS is the only one."""
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(guard.operator_settings, "has_org_surface", lambda: False)
        guard.reject_admin_tenant_content_in_multi_tenant()


def test_admin_cms_blocked_in_multi_tenant() -> None:
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(guard.operator_settings, "has_org_surface", lambda: True)
        with pytest.raises(HTTPException) as exc:
            guard.reject_admin_tenant_content_in_multi_tenant()
        assert exc.value.status_code == 403


def test_admin_rag_tenant_knowledge_blocked_in_multi_tenant() -> None:
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(guard.operator_settings, "has_org_surface", lambda: True)
        with pytest.raises(HTTPException) as exc:
            guard.reject_admin_tenant_knowledge_rag_ingest("tenant_knowledge")
        assert exc.value.status_code == 403


def test_admin_rag_agentlayer_docs_allowed_in_multi_tenant() -> None:
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(guard.operator_settings, "has_org_surface", lambda: True)
        guard.reject_admin_tenant_knowledge_rag_ingest("agentlayer_docs")


def test_admin_rag_tenant_knowledge_allowed_without_org_surface() -> None:
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(guard.operator_settings, "has_org_surface", lambda: False)
        guard.reject_admin_tenant_knowledge_rag_ingest("tenant_knowledge")
