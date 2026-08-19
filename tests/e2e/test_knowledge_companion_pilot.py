"""
Knowledge Companion pilot E2E — automates Phase 7 test plan (P02–P09).

Uses HTTP APIs only (no Playwright). Chat quality / LLM citations stay optional;
RAG isolation and CMS workflow are fully asserted here.

Run:
  ./scripts/run-e2e-journeys.sh
  # or
  pytest tests/e2e/test_knowledge_companion_pilot.py -m e2e -v
"""

from __future__ import annotations

import uuid

import httpx
import pytest

from tests.e2e.support.helpers import E2EClient
from tests.e2e.support.pilot import (
    PilotSandbox,
    hits_contain_marker,
    rag_ready,
    rag_search,
    require_multi_tenant,
)

pytestmark = pytest.mark.e2e


@pytest.fixture
def pilot_sandbox(admin_client: E2EClient):
    sandbox = PilotSandbox.provision(admin_client)
    try:
        yield sandbox
    finally:
        sandbox.close()


def test_pilot_tenant_templates_list(admin_client: E2EClient, e2e_server: None) -> None:
    """P08 — template catalog (requires ``content/tenant-templates`` in server image)."""
    items = admin_client.get_json("/v1/admin/tenant-templates").get("items") or []
    ids = {row.get("id") for row in items if isinstance(row, dict)}
    if not ids:
        pytest.skip(
            "no tenant templates on server — rebuild Docker after COPY content/ or run API from repo root"
        )
    assert "tpl_default_ops" in ids
    assert "tpl_ops_hub" in ids
    # Operator-local templates (content/_private/tenant-templates) are optional on CI images.
    if "tpl_healthcare_ops" not in ids:
        pytest.skip("operator-local tpl_healthcare_ops not present in this environment")


def test_pilot_org_setup_required_gate(
    admin_client: E2EClient,
    e2e_server: None,
) -> None:
    """P02 — setup_required until wizard completes."""
    require_multi_tenant(admin_client)
    suffix = uuid.uuid4().hex[:8]
    created = admin_client.post_json(
        "/v1/admin/tenants",
        {"name": f"e2e-kc-setup-{suffix}"},
    )
    tenant_id = int((created.get("tenant") or {}).get("id") or 0)
    assert tenant_id >= 2

    pwd = f"E2eSetup-{uuid.uuid4().hex[:12]}!"
    email = f"e2e-kc-setup-ta-{suffix}@example.com"
    from tests.e2e.support.pilot import attach_user_to_tenant, complete_org_setup

    ta = attach_user_to_tenant(
        admin_client,
        email=email,
        password=pwd,
        tenant_id=tenant_id,
        membership="tenant_admin",
    )
    try:
        me = ta.get_json("/auth/me")
        assert me.get("org_setup_required") is True

        tenant = ta.get_json("/v1/org/tenant")
        assert tenant.get("setup_required") is True

        complete_org_setup(ta)
        me2 = ta.get_json("/auth/me")
        assert me2.get("org_setup_required") is False
    finally:
        ta.close()


def test_pilot_review_workflow_chain(pilot_sandbox: PilotSandbox, e2e_server: None) -> None:
    """P04 — draft → in_review → approved → published + audit."""
    sb = pilot_sandbox
    marker = sb.marker
    title = f"OP checklist {marker}"

    created = sb.editor.post_json(
        "/v1/org/tenant-content",
        {
            "title": title,
            "body_md": f"Replace tubing every 7 days. {marker}",
            "vertical_profile": "healthcare_ops",
        },
    )
    content_id = str((created.get("content") or {}).get("id") or "")
    assert content_id

    pub_resp = sb.editor.http.post(f"/v1/org/tenant-content/{content_id}/publish")
    assert pub_resp.status_code == 409, pub_resp.text[:300]

    sb.editor.post_json(f"/v1/org/tenant-content/{content_id}/submit-for-review")

    queue = sb.reviewer.get_json("/v1/org/tenant-content/review-queue")
    ids = {str(row.get("id")) for row in (queue.get("items") or []) if isinstance(row, dict)}
    assert content_id in ids

    reject_resp = sb.reviewer.http.post(
        f"/v1/org/tenant-content/{content_id}/reject",
        json={"comment": "  "},
    )
    assert reject_resp.status_code == 400

    sb.reviewer.post_json(
        f"/v1/org/tenant-content/{content_id}/reject",
        {"comment": "Kürzer formulieren"},
    )

    sb.editor.patch_json(
        f"/v1/org/tenant-content/{content_id}",
        {"body_md": f"Wechsel alle 7 Tage. {marker}"},
    )
    sb.editor.post_json(f"/v1/org/tenant-content/{content_id}/submit-for-review")
    sb.reviewer.post_json(f"/v1/org/tenant-content/{content_id}/approve")
    pub = sb.approver.post_json(f"/v1/org/tenant-content/{content_id}/publish")
    assert (pub.get("content") or {}).get("status") == "published"

    audit = sb.editor.get_json(f"/v1/org/tenant-content/{content_id}/audit")
    events = {row.get("event_type") for row in (audit.get("items") or []) if isinstance(row, dict)}
    assert "submit_for_review" in events
    assert "reject" in events
    assert "approve" in events
    assert "publish" in events

    result = rag_search(sb.end_user_nurse, marker)
    assert result.get("ok") is True, result
    assert hits_contain_marker(result.get("hits") or [], marker), result


def test_pilot_profession_rag_filter(pilot_sandbox: PilotSandbox, e2e_server: None) -> None:
    """P05 — OTA-only note visible to OTA, not anesthesia nurse."""
    sb = pilot_sandbox
    marker = f"{sb.marker}-ota-only"
    title = f"OTA SOP {marker}"

    created = sb.editor.post_json(
        "/v1/org/tenant-content",
        {
            "title": title,
            "body_md": f"OTA sterile field protocol. {marker}",
            "vertical_profile": "healthcare_ops",
            "target_profession_roles": ["ota"],
        },
    )
    content_id = str((created.get("content") or {}).get("id") or "")
    sb.editor.post_json(f"/v1/org/tenant-content/{content_id}/submit-for-review")
    sb.reviewer.post_json(f"/v1/org/tenant-content/{content_id}/approve")
    sb.approver.post_json(f"/v1/org/tenant-content/{content_id}/publish")

    ota_hits = rag_search(sb.end_user_ota, marker).get("hits") or []
    nurse_hits = rag_search(sb.end_user_nurse, marker).get("hits") or []
    assert hits_contain_marker(ota_hits, marker), ota_hits
    assert not hits_contain_marker(nurse_hits, marker), nurse_hits


def test_pilot_healthcare_phi_publish_blocked(
    pilot_sandbox: PilotSandbox,
    e2e_server: None,
) -> None:
    """P09 — PHI patterns blocked on publish for healthcare_ops."""
    sb = pilot_sandbox
    created = sb.editor.post_json(
        "/v1/org/tenant-content",
        {
            "title": "PHI probe",
            "body_md": "Patient Schmidt wurde heute behandelt.",
            "vertical_profile": "healthcare_ops",
        },
    )
    content_id = str((created.get("content") or {}).get("id") or "")
    sb.editor.post_json(f"/v1/org/tenant-content/{content_id}/submit-for-review")
    sb.reviewer.post_json(f"/v1/org/tenant-content/{content_id}/approve")

    resp = sb.approver.http.post(f"/v1/org/tenant-content/{content_id}/publish")
    assert resp.status_code == 400, resp.text[:400]
    assert "patient" in resp.text.lower()


def test_pilot_knowledge_companion_agent_accessible(
    pilot_sandbox: PilotSandbox,
    e2e_server: None,
) -> None:
    """P06 (minimal) — end user can call knowledge_companion (not blocked by access guard)."""
    sb = pilot_sandbox
    resp = sb.end_user_nurse.http.post(
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


def test_pilot_cross_tenant_isolation_via_cms(
    admin_client: E2EClient,
    e2e_server: None,
) -> None:
    """P07 — published CMS content not visible in another tenant."""
    rag_ready(admin_client)
    require_multi_tenant(admin_client)
    sb = PilotSandbox.provision(admin_client)
    try:
        marker = f"{sb.marker}-iso"
        created = sb.editor.post_json(
            "/v1/org/tenant-content",
            {
                "title": f"Secret {marker}",
                "body_md": f"Tenant-only secret. {marker}",
                "vertical_profile": "healthcare_ops",
            },
        )
        content_id = str((created.get("content") or {}).get("id") or "")
        sb.editor.post_json(f"/v1/org/tenant-content/{content_id}/submit-for-review")
        sb.reviewer.post_json(f"/v1/org/tenant-content/{content_id}/approve")
        sb.approver.post_json(f"/v1/org/tenant-content/{content_id}/publish")

        other_tenant = admin_client.post_json(
            "/v1/admin/tenants",
            {"name": f"e2e-kc-other-{uuid.uuid4().hex[:8]}"},
        )
        other_id = int((other_tenant.get("tenant") or {}).get("id") or 0)
        email = f"e2e-kc-other-{uuid.uuid4().hex[:8]}@example.com"
        password = f"E2eOther-{uuid.uuid4().hex[:12]}!"
        admin_client.post_json(
            "/v1/admin/users",
            {"email": email, "password": password, "role": "user", "tenant_id": other_id},
        )
        other = E2EClient.login(email, password)
        try:
            result = rag_search(other, marker)
            assert result.get("ok") is True, result
            assert not hits_contain_marker(result.get("hits") or [], marker), result
        finally:
            other.close()
    finally:
        sb.close()
