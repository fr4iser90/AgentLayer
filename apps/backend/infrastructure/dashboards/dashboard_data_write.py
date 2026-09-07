"""Persist dashboard ``data`` payloads into domain collections (source of truth).

``user_dashboards.data`` only keeps non-content config (see ``RESERVED_DATA_KEYS``);
board content lives in collections and is written here per block ``dataPath``.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from apps.backend.domain.collections.bindings import RESERVED_DATA_KEYS
from apps.backend.infrastructure.collections import collections_view_service as domain_svc
from apps.backend.infrastructure.dashboards.dashboard_data_paths import get_path, top_level_key

logger = logging.getLogger(__name__)


def split_reserved_data(
    data: dict[str, Any] | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Split a ``data`` payload into ``(board_content, reserved_config)``."""
    if not isinstance(data, dict):
        return {}, {}
    content: dict[str, Any] = {}
    reserved: dict[str, Any] = {}
    for key, value in data.items():
        if str(key) in RESERVED_DATA_KEYS:
            reserved[str(key)] = value
        else:
            content[str(key)] = value
    return content, reserved


def write_dashboard_data(
    *,
    dashboard_id: uuid.UUID,
    owner_user_id: uuid.UUID,
    tenant_id: int,
    ui_layout: dict[str, Any] | None,
    view_bindings: dict[str, Any] | None,
    template_id: str | None,
    data: dict[str, Any],
    allowed_top_keys: set[str] | None = None,
) -> dict[str, Any]:
    """Write every bound ``dataPath`` present in ``data`` into its collection.

    Paths missing from ``data`` are left untouched so partial saves cannot wipe
    lists the client never loaded.
    """
    if not isinstance(data, dict) or not data:
        return {"ok": True, "applied": [], "errors": []}

    ws = {
        "id": str(dashboard_id),
        "owner_user_id": str(owner_user_id),
        "tenant_id": int(tenant_id),
        "ui_layout": ui_layout if isinstance(ui_layout, dict) else {},
        "view_bindings": view_bindings if isinstance(view_bindings, dict) else {},
        "template_id": template_id,
    }
    bindings = domain_svc.resolve_bindings_for_dashboard(ws)

    patches: list[dict[str, Any]] = []
    for path in bindings:
        if allowed_top_keys is not None and top_level_key(path) not in allowed_top_keys:
            continue
        value = get_path(data, path)
        if value is None:
            continue
        patches.append({"path": path, "value": value})

    if not patches:
        return {"ok": True, "applied": [], "errors": []}

    result = domain_svc.patch_fields(
        owner_user_id=owner_user_id,
        tenant_id=int(tenant_id),
        bindings=bindings,
        ui_layout=ws["ui_layout"],
        patches=patches,
    )
    if not result.get("ok"):
        logger.warning(
            "dashboard_data_write failed for %s: %s",
            dashboard_id,
            result.get("error"),
        )
    return result
