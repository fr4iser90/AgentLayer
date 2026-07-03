"""Provision live tenants from templates (Task 07)."""

from __future__ import annotations

import re
import uuid
from pathlib import Path
from typing import Any

from apps.backend.application.tenant_content.use_cases import tenant_content_service as cms
from apps.backend.application.tenant_provisioning.use_cases.tenant_template_loader import (
    get_template,
    resolve_seed_paths,
)
from apps.backend.application.tenant_provisioning.use_cases.tenant_capability_policy import (
    apply_template_capability_config,
)
from apps.backend.domain.tenant_templates.entities import TenantTemplate
from apps.backend.infrastructure.db import db


def apply_template_profession_config(tenant_id: int, template: TenantTemplate) -> None:
    for dept in template.departments:
        if not db.department_get_by_slug(tenant_id, dept.slug):
            db.department_insert(tenant_id, dept.slug, dept.name)
    for role in template.profession_roles:
        if not db.profession_role_get_by_slug(tenant_id, role.slug):
            db.profession_role_insert(
                tenant_id,
                role.slug,
                role.name,
                role.role_kind,
                list(role.content_categories),
            )


def _title_from_markdown(path: Path, body: str) -> str:
    for line in body.splitlines():
        m = re.match(r"^#\s+(.+)$", line.strip())
        if m:
            return m.group(1).strip()[:512]
    stem = path.stem.replace("-", " ").replace("_", " ").strip()
    return (stem or path.name)[:512]


def seed_demo_content(
    *,
    tenant_id: int,
    template: TenantTemplate,
    actor_user_id: uuid.UUID,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for path in resolve_seed_paths(template.seed_content_glob):
        if not path.is_file() or path.suffix.lower() not in (".md", ".markdown", ".txt"):
            continue
        body = path.read_text(encoding="utf-8").strip()
        if not body:
            continue
        title = _title_from_markdown(path, body)
        row = cms.create_draft(
            tenant_id=tenant_id,
            user_id=actor_user_id,
            title=title,
            body_md=body,
            vertical_profile=template.vertical_profile,
        )
        cid = uuid.UUID(str(row["id"]))
        pub = cms.publish_content(
            tenant_id=tenant_id,
            user_id=actor_user_id,
            content_id=cid,
            override=True,
        )
        out.append(
            {
                "path": str(path.name),
                "content_id": str(row["id"]),
                "title": title,
                "rag_chunks": pub.get("rag", {}).get("chunk_count"),
            }
        )
    return out


def provision_tenant(
    *,
    name: str,
    template_id: str | None = None,
    seed_demo_content: bool = False,
    actor_user_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    label = (name or "").strip() or "tenant"
    row = db.tenant_insert(label)
    tenant_id = int(row["id"])
    applied_template: TenantTemplate | None = None

    if template_id:
        applied_template = get_template(template_id)
        db.tenant_update_org_profile(tenant_id, vertical_profile=applied_template.vertical_profile)
        apply_template_profession_config(tenant_id, applied_template)
        apply_template_capability_config(
            tenant_id,
            applied_template,
            actor_user_id=actor_user_id,
        )

    seeded: list[dict[str, Any]] = []
    if seed_demo_content:
        if not applied_template:
            raise ValueError("seed_demo_content requires template_id")
        uid = actor_user_id or db.user_first_admin_id()
        if uid is None:
            raise ValueError("seed_demo_content requires a site admin user to publish seed notes")
        seeded = seed_demo_content(tenant_id=tenant_id, template=applied_template, actor_user_id=uid)

    tenant = db.tenant_get(tenant_id) or row
    return {
        "tenant": tenant,
        "template_id": applied_template.id if applied_template else None,
        "seeded_content": seeded,
    }
