from __future__ import annotations

import logging
from typing import Any

from apps.backend.domain.plugin_system.tool_manifest_dimensions import (
    normalize_execution_context,
    normalize_min_role,
    normalize_risk_level,
    parse_allowed_tenant_ids,
    parse_os_support,
)

logger = logging.getLogger(__name__)

_ALLOWED_ADMIN_BUCKETS = frozenset(
    {
        "files",
        "network",
        "knowledge",
        "secrets",
        "comms",
        "verticals",
        "meta",
        "media",
        "productivity",
        "unsorted",
    }
)


def _apply_admin_ui_metadata(mod: Any, entry: dict[str, Any]) -> None:
    """``admin_bucket`` / ``admin_tags`` from the tool module only."""
    pid = str(entry.get("id") or "").strip()
    raw_b = getattr(mod, "TOOL_BUCKET", None)
    bucket = (
        str(raw_b).strip().lower()
        if isinstance(raw_b, str) and raw_b.strip()
        else "unsorted"
    )
    if bucket not in _ALLOWED_ADMIN_BUCKETS:
        logger.warning("unknown TOOL_BUCKET %r for %s — using unsorted", raw_b, pid)
        bucket = "unsorted"
    entry["admin_bucket"] = bucket

    at = getattr(mod, "TOOL_ADMIN_TAGS", None)
    if isinstance(at, (list, tuple, frozenset, set)):
        tags = [str(x).strip() for x in at if str(x).strip()]
        if tags:
            entry["admin_tags"] = tags
    elif isinstance(at, str) and at.strip():
        entry["admin_tags"] = [
            x.strip() for x in at.replace(";", ",").split(",") if x.strip()
        ]


def _apply_manifest_extras(mod: Any, entry: dict[str, Any]) -> None:
    """Optional module fields for execution context, capabilities, security, and UI."""
    xctx = getattr(mod, "TOOL_EXECUTION_CONTEXT", None)
    entry["execution_context"] = normalize_execution_context(
        xctx if isinstance(xctx, str) else None
    )
    oss = parse_os_support(mod)
    if oss:
        entry["os_support"] = oss
    rlv = getattr(mod, "TOOL_RISK_LEVEL", None)
    nr = normalize_risk_level(rlv)
    if nr:
        entry["risk_level"] = nr

    caps = getattr(mod, "TOOL_CAPABILITIES", None)
    if isinstance(caps, (list, tuple, frozenset, set)):
        lc = [str(x).strip() for x in caps if str(x).strip()]
        if lc:
            entry["capabilities"] = lc
    req = getattr(mod, "TOOL_SECRETS_REQUIRED", None)
    if isinstance(req, (list, tuple, frozenset, set)):
        lr = [str(x).strip() for x in req if str(x).strip()]
        if lr:
            entry["secrets_required"] = lr
    mr = getattr(mod, "TOOL_MIN_ROLE", None)
    entry["min_role"] = normalize_min_role(mr if isinstance(mr, str) else None)
    at = getattr(mod, "TOOL_ALLOWED_TENANT_IDS", None)
    entry["allowed_tenant_ids"] = parse_allowed_tenant_ids(at)
    fam = getattr(mod, "TOOL_FAMILIES", None)
    if isinstance(fam, (list, tuple, frozenset, set)):
        lf = [str(x).strip() for x in fam if str(x).strip()]
        if lf:
            entry["families"] = lf
    usf = getattr(mod, "TOOL_USER_SECRET_FORMS", None)
    if isinstance(usf, dict) and usf:
        cleaned: dict[str, Any] = {}
        for k, v in usf.items():
            sk = str(k).strip().lower()
            if sk and isinstance(v, dict):
                cleaned[sk] = v
        if cleaned:
            entry["user_secret_forms"] = cleaned


__all__ = ["_ALLOWED_ADMIN_BUCKETS", "_apply_admin_ui_metadata", "_apply_manifest_extras"]
