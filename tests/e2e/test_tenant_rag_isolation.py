"""
E2E tenant RAG isolation — Task 03 (no LLM required).

Uses ``POST /tools/run`` with ``rag_search`` after admin ingest.
"""

from __future__ import annotations

import json
import uuid

import httpx
import pytest

from tests.e2e.support.helpers import E2EClient

pytestmark = pytest.mark.e2e

E2E_RAG_PREFIX = "[E2E RAG T03]"


def _rag_ready(client: E2EClient) -> None:
    if client.role != "admin":
        pytest.skip("admin client required to read operator settings")
    settings = client.get_json("/v1/admin/operator-settings")
    if not settings.get("rag_enabled"):
        pytest.skip("RAG disabled in operator settings")
    domains = str(settings.get("rag_tenant_shared_domains") or "")
    if "tenant_knowledge" not in domains:
        pytest.skip("tenant_knowledge not in rag_tenant_shared_domains")


def _rag_search(client: E2EClient, query: str) -> dict:
    resp = client.http.post(
        "/tools/run",
        json={
            "name": "rag_search",
            "arguments": {"query": query, "domain": "tenant_knowledge", "limit": 5},
        },
    )
    assert resp.status_code == 200, resp.text[:400]
    data = resp.json()
    result_raw = data.get("result")
    if isinstance(result_raw, str):
        return json.loads(result_raw)
    if isinstance(result_raw, dict):
        return result_raw
    return data


def _hits_contain_marker(hits: list[dict], marker: str) -> bool:
    blob = json.dumps(hits, ensure_ascii=False).lower()
    return marker.lower() in blob


def test_user_b_knowledge_companion_chat_not_blocked(
    e2e_server: None,
    user_b_client: E2EClient,
) -> None:
    """End users may select knowledge_companion (access guard must not reject)."""
    resp = user_b_client.http.post(
        "/v1/chat/completions",
        json={
            "model": "general",
            "agent_id": "knowledge_companion",
            "messages": [{"role": "user", "content": "hello"}],
        },
    )
    if resp.status_code in (400, 403):
        err = resp.text.lower()
        assert "not available" not in err, resp.text[:400]
        return
    assert resp.status_code in (200, 502, 503), resp.text[:300]


def test_same_tenant_user_finds_tenant_knowledge(
    e2e_server: None,
    admin_client: E2EClient,
    user_b_client: E2EClient,
) -> None:
    _rag_ready(admin_client)
    marker = f"{E2E_RAG_PREFIX} same-tenant {uuid.uuid4().hex[:10]}"
    ingest = admin_client.post_json(
        "/v1/admin/rag/ingest",
        {
            "text": f"Operational note: {marker} — replace ventilation tubing every 7 days.",
            "domain": "tenant_knowledge",
            "title": f"E2E note {marker}",
            "source_uri": f"e2e://t03/{marker}",
        },
    )
    assert ingest.get("ok") is True, ingest

    result = _rag_search(user_b_client, marker)
    assert result.get("ok") is True, result
    hits = result.get("hits") or []
    assert _hits_contain_marker(hits, marker), hits


def test_cross_tenant_user_cannot_see_other_tenant_knowledge(
    e2e_server: None,
    admin_client: E2EClient,
) -> None:
    _rag_ready(admin_client)
    marker = f"{E2E_RAG_PREFIX} cross-tenant {uuid.uuid4().hex[:10]}"
    ingest = admin_client.post_json(
        "/v1/admin/rag/ingest",
        {
            "text": f"Secret tenant note: {marker}",
            "domain": "tenant_knowledge",
            "title": f"E2E isolated {marker}",
            "source_uri": f"e2e://t03/{marker}",
        },
    )
    assert ingest.get("ok") is True, ingest

    tenant_name = f"e2e-rag-{uuid.uuid4().hex[:8]}"
    created = admin_client.post_json("/v1/admin/tenants", {"name": tenant_name})
    tenant_id = int((created.get("tenant") or {}).get("id") or 0)
    assert tenant_id >= 2, created

    email = f"e2e-t{tenant_id}-{uuid.uuid4().hex[:8]}@example.com"
    password = f"E2eT3-{uuid.uuid4().hex[:12]}!"
    admin_client.post_json(
        "/v1/admin/users",
        {"email": email, "password": password, "role": "user", "tenant_id": tenant_id},
    )

    try:
        other = E2EClient.login(email, password)
    except httpx.HTTPStatusError as exc:
        pytest.fail(f"could not login tenant-2 user: {exc}")

    try:
        result = _rag_search(other, marker)
        assert result.get("ok") is True, result
        hits = result.get("hits") or []
        assert not _hits_contain_marker(hits, marker), hits
    finally:
        other.close()
