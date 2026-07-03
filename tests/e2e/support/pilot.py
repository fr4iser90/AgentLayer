"""Helpers for Knowledge Companion pilot E2E (Tasks 03–07)."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field

import httpx
import pytest

from tests.e2e.support.helpers import E2EClient

E2E_PILOT_PREFIX = "[E2E KC PILOT]"


def rag_ready(client: E2EClient) -> None:
    if client.role != "admin":
        pytest.skip("admin client required to read operator settings")
    settings = client.get_json("/v1/admin/operator-settings")
    if not settings.get("rag_enabled"):
        pytest.skip("RAG disabled in operator settings")
    domains = str(settings.get("rag_tenant_shared_domains") or "")
    if "tenant_knowledge" not in domains:
        pytest.skip("tenant_knowledge not in rag_tenant_shared_domains")


def require_multi_tenant(admin: E2EClient) -> str:
    settings = admin.get_json("/v1/admin/operator-settings")
    mode = str(settings.get("deployment_mode") or "multi_tenant").strip().lower()
    if mode != "multi_tenant":
        pytest.skip(f"multi_tenant deployment required (got {mode!r})")
    return mode


def rag_search(client: E2EClient, query: str) -> dict:
    resp = client.http.post(
        "/tools/run",
        json={
            "name": "rag_search",
            "arguments": {"query": query, "domain": "tenant_knowledge", "limit": 8},
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


def hits_contain_marker(hits: list[dict], marker: str) -> bool:
    blob = json.dumps(hits, ensure_ascii=False).lower()
    return marker.lower() in blob


def attach_user_to_tenant(
    admin: E2EClient,
    *,
    email: str,
    password: str,
    tenant_id: int,
    membership: str = "tenant_member",
) -> E2EClient:
    """Create user via admin API and ensure tenant membership (no public membership API)."""
    from apps.backend.infrastructure.db import db
    from apps.backend.infrastructure.identity.auth import get_user_by_email, update_user_tenant

    admin.post_json_allow(
        "/v1/admin/users",
        {"email": email, "password": password, "role": "user", "tenant_id": tenant_id},
        ok={200, 409},
    )
    user = get_user_by_email(email)
    if not user:
        raise RuntimeError(f"user not found after create: {email}")
    update_user_tenant(user.id, tenant_id)
    db.tenant_membership_upsert(user.id, tenant_id, membership)
    return E2EClient.login(email, password)


def profession_role_id(client: E2EClient, slug: str) -> str:
    items = client.get_json("/v1/org/profession-roles").get("items") or []
    for row in items:
        if isinstance(row, dict) and row.get("slug") == slug:
            return str(row["id"])
    raise KeyError(f"profession role not found: {slug}")


def assign_profession_role(
    tenant_admin: E2EClient,
    *,
    user_id: str,
    role_slug: str,
) -> None:
    role_id = profession_role_id(tenant_admin, role_slug)
    tenant_admin.http.put(
        "/v1/org/profession-assignments",
        json={"user_id": user_id, "profession_role_id": role_id},
    ).raise_for_status()


def complete_org_setup(tenant_admin: E2EClient, *, start_empty: bool = True) -> None:
    tenant_admin.post_json(
        "/v1/org/setup/complete",
        {
            "disclaimer_accepted": True,
            "start_empty": start_empty,
            "published_note": not start_empty,
        },
    )


@dataclass
class PilotSandbox:
    tenant_id: int
    tenant_admin: E2EClient
    editor: E2EClient
    reviewer: E2EClient
    approver: E2EClient
    end_user_nurse: E2EClient
    end_user_ota: E2EClient
    marker: str
    _clients: list[E2EClient] = field(default_factory=list)

    def close(self) -> None:
        for client in self._clients:
            client.close()

    @classmethod
    def provision(
        cls,
        admin: E2EClient,
        *,
        template_id: str = "tpl_healthcare_ops",
    ) -> PilotSandbox:
        require_multi_tenant(admin)
        rag_ready(admin)
        suffix = uuid.uuid4().hex[:8]
        marker = f"{E2E_PILOT_PREFIX} {suffix}"
        tenant_name = f"e2e-kc-pilot-{suffix}"
        templates = admin.get_json("/v1/admin/tenant-templates").get("items") or []
        known = {row.get("id") for row in templates if isinstance(row, dict)}
        body: dict = {"name": tenant_name}
        if template_id in known:
            body["template_id"] = template_id
        created = admin.post_json("/v1/admin/tenants", body)
        tenant_id = int((created.get("tenant") or {}).get("id") or 0)
        assert tenant_id >= 2, created

        pwd = f"E2eKc-{uuid.uuid4().hex[:12]}!"
        ta_email = f"e2e-kc-ta-{suffix}@example.com"
        tenant_admin = attach_user_to_tenant(
            admin,
            email=ta_email,
            password=pwd,
            tenant_id=tenant_id,
            membership="tenant_admin",
        )

        editor = attach_user_to_tenant(
            admin,
            email=f"e2e-kc-ed-{suffix}@example.com",
            password=pwd,
            tenant_id=tenant_id,
        )
        reviewer = attach_user_to_tenant(
            admin,
            email=f"e2e-kc-rev-{suffix}@example.com",
            password=pwd,
            tenant_id=tenant_id,
        )
        approver = attach_user_to_tenant(
            admin,
            email=f"e2e-kc-apr-{suffix}@example.com",
            password=pwd,
            tenant_id=tenant_id,
        )
        nurse = attach_user_to_tenant(
            admin,
            email=f"e2e-kc-nurse-{suffix}@example.com",
            password=pwd,
            tenant_id=tenant_id,
        )
        ota = attach_user_to_tenant(
            admin,
            email=f"e2e-kc-ota-{suffix}@example.com",
            password=pwd,
            tenant_id=tenant_id,
        )

        assign_profession_role(tenant_admin, user_id=editor.user_id, role_slug="content_editor")
        assign_profession_role(tenant_admin, user_id=reviewer.user_id, role_slug="content_reviewer")
        assign_profession_role(tenant_admin, user_id=approver.user_id, role_slug="content_approver")
        assign_profession_role(tenant_admin, user_id=nurse.user_id, role_slug="anesthesia_nurse")
        assign_profession_role(tenant_admin, user_id=ota.user_id, role_slug="ota")

        complete_org_setup(tenant_admin)

        # Seed default profession roles when no template was applied.
        tenant_admin.get_json("/v1/org/profession-roles")

        clients = [tenant_admin, editor, reviewer, approver, nurse, ota]
        return cls(
            tenant_id=tenant_id,
            tenant_admin=tenant_admin,
            editor=editor,
            reviewer=reviewer,
            approver=approver,
            end_user_nurse=nurse,
            end_user_ota=ota,
            marker=marker,
            _clients=clients,
        )
