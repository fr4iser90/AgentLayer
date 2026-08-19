"""Load tenant templates from JSON (Task 07)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from apps.backend.domain.tenant_templates.entities import (
    TemplateDepartment,
    TemplateProfessionRole,
    TenantTemplate,
)

_REPO_ROOT = Path(__file__).resolve().parents[5]
_TEMPLATES_DIR = _REPO_ROOT / "content" / "tenant-templates"
# Operator-local templates (gitignored under content/_private/) — same schema, not published.
_PRIVATE_TEMPLATES_DIR = _REPO_ROOT / "content" / "_private" / "tenant-templates"
_CACHE: dict[str, TenantTemplate] | None = None


def templates_dir() -> Path:
    return _TEMPLATES_DIR


def template_search_dirs() -> list[Path]:
    return [_TEMPLATES_DIR, _PRIVATE_TEMPLATES_DIR]


def _parse_template(raw: dict[str, Any]) -> TenantTemplate:
    tid = str(raw.get("id") or "").strip()
    if not tid:
        raise ValueError("template id is required")
    depts = tuple(
        TemplateDepartment(slug=str(d["slug"]), name=str(d["name"]))
        for d in (raw.get("departments") or [])
        if isinstance(d, dict) and d.get("slug")
    )
    roles = tuple(
        TemplateProfessionRole(
            slug=str(r["slug"]),
            name=str(r["name"]),
            role_kind=str(r.get("role_kind") or "end_user"),
            content_categories=tuple(str(c) for c in (r.get("content_categories") or []) if str(c).strip()),
        )
        for r in (raw.get("profession_roles") or [])
        if isinstance(r, dict) and r.get("slug")
    )
    seed = raw.get("seed_content_glob")
    agents = tuple(
        str(x).strip()
        for x in (raw.get("enabled_agent_ids") or [])
        if isinstance(x, (str, int)) and str(x).strip()
    )
    tool_domains = tuple(
        str(x).strip().lower()
        for x in (raw.get("enabled_tool_domains") or [])
        if isinstance(x, (str, int)) and str(x).strip()
    )
    dashboard_kinds = tuple(
        str(x).strip().lower()
        for x in (raw.get("enabled_dashboard_kinds") or [])
        if isinstance(x, (str, int)) and str(x).strip()
    )
    nav_items = tuple(
        str(x).strip().lower()
        for x in (raw.get("enabled_nav_items") or [])
        if isinstance(x, (str, int)) and str(x).strip()
    )
    write_roles = tuple(
        str(x).strip().lower()
        for x in (raw.get("enabled_dashboard_write_roles") or [])
        if isinstance(x, (str, int)) and str(x).strip()
    )
    return TenantTemplate(
        id=tid,
        name=str(raw.get("name") or tid),
        description=str(raw.get("description") or ""),
        vertical_profile=str(raw.get("vertical_profile") or "default_ops"),
        departments=depts,
        profession_roles=roles,
        workflow_defaults=dict(raw.get("workflow_defaults") or {}),
        seed_content_glob=str(seed).strip() if seed else None,
        enabled_agent_ids=agents,
        enabled_tool_domains=tool_domains,
        enabled_dashboard_kinds=dashboard_kinds,
        enabled_nav_items=nav_items,
        enabled_dashboard_write_roles=write_roles,
    )


def load_all_templates(*, reload: bool = False) -> dict[str, TenantTemplate]:
    global _CACHE
    if _CACHE is not None and not reload:
        return _CACHE
    out: dict[str, TenantTemplate] = {}
    for directory in template_search_dirs():
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.json")):
            raw = json.loads(path.read_text(encoding="utf-8"))
            tpl = _parse_template(raw)
            # Later dirs win (private overlays public id if both exist).
            out[tpl.id] = tpl
    _CACHE = out
    return out


def list_templates_public() -> list[dict[str, Any]]:
    return [t.to_public_dict() for t in sorted(load_all_templates().values(), key=lambda x: x.id)]


def get_template(template_id: str) -> TenantTemplate:
    tid = (template_id or "").strip()
    if not tid:
        raise HTTPException(status_code=400, detail="template_id is required")
    tpl = load_all_templates().get(tid)
    if not tpl:
        known = ", ".join(sorted(load_all_templates()))
        raise HTTPException(status_code=400, detail=f"unknown template_id {tid!r} — known: {known or '(none)'}")
    return tpl


def resolve_seed_paths(seed_glob: str | None) -> list[Path]:
    if not seed_glob:
        return []
    pattern = seed_glob.strip()
    if not pattern:
        return []
    base = _REPO_ROOT
    if pattern.startswith("content/"):
        return sorted(base.glob(pattern))
    return sorted(Path(pattern).glob("**/*.md") if "*" not in pattern else base.glob(pattern))
