"""Admin tools inventory (domain / provider overview)."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from fastapi import APIRouter, Query, Request

from apps.backend.domain.plugin_system.registry import get_registry
from apps.backend.application.identity.use_cases.request_auth import require_admin

router = APIRouter(tags=["admin-tools"])


@router.get("/v1/admin/tools/domains")
async def admin_tools_domains(
    request: Request,
    domain: str | None = Query(None, description="Filter by TOOL_DOMAIN"),
) -> dict[str, Any]:
    """Grouped tool inventory with optional provider metadata."""
    await require_admin(request)
    reg = get_registry()
    want = (domain or "").strip().lower()

    by_domain: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for entry in reg.tools_meta:
        dom = str(entry.get("domain") or "?").lower()
        if want and dom != want:
            continue
        provider = entry.get("provider")
        pkg = str(entry.get("id") or "")
        for name in entry.get("tools") or []:
            if not name:
                continue
            row: dict[str, Any] = {"tool_name": name, "package_id": pkg}
            if provider:
                row["provider"] = provider
            caps = entry.get("capabilities")
            if caps:
                row["capabilities"] = caps
            by_domain[dom].append(row)

    domains_out = {
        d: {"count": len(rows), "tools": sorted(rows, key=lambda r: r["tool_name"])}
        for d, rows in sorted(by_domain.items())
    }
    total = sum(len(v["tools"]) for v in domains_out.values())
    return {"domains": domains_out, "domain_count": len(domains_out), "tool_count": total}
