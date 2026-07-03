"""Guardrails: platform admin vs organization surfaces (Task 03b)."""

from __future__ import annotations

from fastapi import HTTPException

from apps.backend.infrastructure.settings import operator_settings

_TENANT_KNOWLEDGE_DOMAINS = frozenset({"tenant_knowledge", "tenant_knowledge_draft"})


def reject_admin_tenant_content_in_multi_tenant() -> None:
    """Team CMS belongs on ``/v1/org/*`` when the product runs in multi_tenant mode."""
    if operator_settings.deployment_mode() != "multi_tenant":
        return
    raise HTTPException(
        status_code=403,
        detail=(
            "Organization knowledge is managed under /v1/org/tenant-content in multi_tenant mode. "
            "Use Organization → Knowledge, not Platform admin."
        ),
    )


def reject_admin_tenant_knowledge_rag_ingest(domain: str | None) -> None:
    """Block legacy admin ingest for tenant team domains in multi_tenant mode."""
    if operator_settings.deployment_mode() != "multi_tenant":
        return
    dom = (domain or "").strip().lower()
    if dom in _TENANT_KNOWLEDGE_DOMAINS:
        raise HTTPException(
            status_code=403,
            detail=(
                "Publish team knowledge via Organization CMS (/v1/org/tenant-content) in multi_tenant mode. "
                "Platform admin RAG ingest is for operator domains (e.g. agentlayer_docs) only."
            ),
        )
