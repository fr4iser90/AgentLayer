from __future__ import annotations

import uuid
import logging
from typing import Any

from psycopg.rows import dict_row
from psycopg.types.json import Json

from apps.backend.infrastructure.db import db
from apps.backend.infrastructure.dashboards.dashboard_layout_tree import (
    data_paths_from_blocks,
    filter_layout_blocks,
)

logger = logging.getLogger(__name__)

def _filter_ui_layout(layout: dict[str, Any], allowed: frozenset[str]) -> dict[str, Any]:
    if not isinstance(layout, dict):
        return {}
    blocks = layout.get("blocks")
    if not isinstance(blocks, list):
        return dict(layout)
    nb = filter_layout_blocks(blocks, allowed)
    out = dict(layout)
    out["blocks"] = nb
    return out


def _data_paths_from_blocks(blocks: list[Any]) -> list[str]:
    return data_paths_from_blocks(blocks)


def _filter_data_for_visible_blocks(
    data: dict[str, Any], filtered_layout: dict[str, Any]
) -> dict[str, Any]:
    blocks = filtered_layout.get("blocks")
    if not isinstance(blocks, list) or not isinstance(data, dict):
        return {}
    paths = _data_paths_from_blocks(blocks)
    keys: set[str] = set()
    for p in paths:
        if not p:
            continue
        keys.add(p.split(".")[0])
    if not keys:
        return {}
    return {k: v for k, v in data.items() if k in keys}


def _allowed_data_keys_from_layout(full_layout: dict[str, Any], allowed: frozenset[str]) -> set[str]:
    blocks = [
        b
        for b in (full_layout.get("blocks") or [])
        if isinstance(b, dict) and str(b.get("id") or "").strip() in allowed
    ]
    paths = _data_paths_from_blocks(blocks)
    keys: set[str] = set()
    for p in paths:
        if not p:
            continue
        keys.add(p.split(".")[0])
    return keys


def _merge_granular_data(
    full_data: dict[str, Any],
    patch: dict[str, Any] | None,
    full_layout: dict[str, Any],
    allowed: frozenset[str],
) -> dict[str, Any]:
    keys = _allowed_data_keys_from_layout(full_layout, allowed)
    out = dict(full_data)
    if not patch:
        return out
    for k in keys:
        if k in patch:
            out[k] = patch[k]
    return out


def _merge_ui_layout_granular(
    full_ul: dict[str, Any], patch_ul: dict[str, Any] | None, allowed: frozenset[str]
) -> dict[str, Any]:
    if not patch_ul:
        return full_ul
    pblocks = patch_ul.get("blocks")
    if not isinstance(pblocks, list):
        return full_ul
    pb_by_id: dict[str, dict[str, Any]] = {}
    for b in pblocks:
        if not isinstance(b, dict):
            continue
        bid = str(b.get("id") or "").strip()
        if bid and bid in allowed:
            pb_by_id[bid] = b
    out_bl: list[Any] = []
    for b in full_ul.get("blocks") or []:
        if not isinstance(b, dict):
            continue
        bid = str(b.get("id") or "").strip()
        if bid in allowed and bid in pb_by_id:
            out_bl.append(pb_by_id[bid])
        else:
            out_bl.append(b)
    out = dict(full_ul)
    out["blocks"] = out_bl
    return out


def _dashboard_update_granular(
    user_id: uuid.UUID,
    tenant_id: int,
    dashboard_id: uuid.UUID,
    *,
    title: str | None,
    ui_layout: dict[str, Any] | None,
    data: dict[str, Any] | None,
    allowed: frozenset[str],
) -> dict[str, Any] | None:
    """Patch only allowed blocks / related data keys; ignore title changes."""
    from apps.backend.infrastructure.dashboards.dashboard_db import (
        _row_dict,
        dashboard_access_ex,
        dashboard_get,
    )

    _ = title
    sets: list[str] = []
    args: list[Any] = []
    with db.pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT ui_layout, data FROM user_dashboards
                WHERE id = %s AND tenant_id = %s
                """,
                (dashboard_id, tenant_id),
            )
            row = cur.fetchone()
            if not row:
                conn.commit()
                return None
            full_ul = row["ui_layout"] if isinstance(row["ui_layout"], dict) else {}
            full_dt = row["data"] if isinstance(row["data"], dict) else {}
            new_ul = full_ul
            new_dt = full_dt
            if data is not None:
                _ = _merge_granular_data(full_dt, data, full_ul, allowed)
                logger.debug(
                    "granular data merge ignored for %s — use domain collections",
                    dashboard_id,
                )
            if ui_layout is not None:
                new_ul = _merge_ui_layout_granular(full_ul, ui_layout, allowed)
            if new_ul == full_ul:
                conn.commit()
                return dashboard_get(user_id, tenant_id, dashboard_id)
            sets.append("ui_layout = %s")
            args.append(Json(new_ul))
            sets.append("updated_at = now()")
            args.extend([dashboard_id, tenant_id, user_id])
            # SECURITY: Column names in `sets` come from function parameters
            # (ui_layout, data). All values are parameterized via %s placeholders.
            cur.execute(
                f"""
                UPDATE user_dashboards w
                SET {", ".join(sets)}
                WHERE w.id = %s AND w.tenant_id = %s
                  AND EXISTS (
                    SELECT 1 FROM dashboard_block_share_grants g
                    WHERE g.dashboard_id = w.id
                      AND g.viewer_user_id = %s
                      AND g.tenant_id = w.tenant_id
                      AND g.permission = 'edit'
                  )
                RETURNING w.id, w.kind, w.template_id, w.title, w.ui_layout, w.data, w.created_at, w.updated_at
                """,
                args,
            )
            urow = cur.fetchone()
        conn.commit()
    if not urow:
        return None
    out = _row_dict(dict(urow))
    d = dashboard_access_ex(user_id, tenant_id, dashboard_id)
    out["access_role"] = d.role or "editor"
    if d.allowed_block_ids is not None:
        ul = out.get("ui_layout") if isinstance(out.get("ui_layout"), dict) else {}
        out["ui_layout"] = _filter_ui_layout(ul, d.allowed_block_ids)
        dt = out.get("data") if isinstance(out.get("data"), dict) else {}
        out["data"] = _filter_data_for_visible_blocks(dt, out["ui_layout"])
        out["access_scope"] = "granular"
        out["allowed_block_ids"] = sorted(d.allowed_block_ids)
        out["granular_can_write"] = d.granular_can_write
    else:
        out["access_scope"] = "full"
    return out


