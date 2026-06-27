"""Public read-only share links for dashboards (optional block scope, password, expiry)."""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime
from typing import Any, Literal, NamedTuple

from psycopg.rows import dict_row

from apps.backend.infrastructure.db import db
from apps.backend.infrastructure.dashboards.dashboard_db import (
    dashboard_can_manage_members,
)
from apps.backend.infrastructure.dashboards.dashboard_granular_update_db import (
    _filter_data_for_visible_blocks,
    _filter_ui_layout,
)
from apps.backend.infrastructure.dashboards.dashboard_members_db import _layout_block_ids

from apps.backend.domain.collections.attachments_db import file_ids_in_value
SHARE_PASSWORD_HEADER = "X-Dashboard-Share-Password"


def hash_share_token(raw: str) -> str:
    return hashlib.sha256(raw.strip().encode("utf-8")).hexdigest()


def hash_share_password(token_hash: str, password: str) -> str:
    payload = f"dashboard-share-pw:{token_hash}:{password.strip()}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class PublicShareViewResult(NamedTuple):
    status: Literal["ok", "not_found", "password_required", "invalid_password"]
    dashboard: dict[str, Any] | None = None
    share_label: str = ""


def _share_row_to_public(row: dict[str, Any]) -> dict[str, Any]:
    bid = row.get("block_ids")
    block_ids = [str(x).strip() for x in bid] if isinstance(bid, list) else []
    exp = row.get("expires_at")
    rev = row.get("revoked_at")
    created = row.get("created_at")
    pw_hash = row.get("password_hash")
    return {
        "id": str(row.get("id") or ""),
        "label": (row.get("label") or "").strip(),
        "block_ids": block_ids,
        "scope": "blocks" if block_ids else "full",
        "expires_at": exp.isoformat() if isinstance(exp, datetime) else None,
        "revoked_at": rev.isoformat() if isinstance(rev, datetime) else None,
        "created_at": created.isoformat() if isinstance(created, datetime) else str(created or ""),
        "password_protected": bool(pw_hash),
    }


def _dashboard_payload_from_row(row: dict[str, Any]) -> dict[str, Any]:
    raw_ids = row.get("block_ids")
    block_ids = [str(x).strip() for x in raw_ids] if isinstance(raw_ids, list) else []
    block_ids = [x for x in block_ids if x]
    ul = row.get("ui_layout") if isinstance(row.get("ui_layout"), dict) else {}
    dt = row.get("data") if isinstance(row.get("data"), dict) else {}
    if block_ids:
        allowed = frozenset(block_ids)
        filtered_ul = _filter_ui_layout(ul, allowed)
        filtered_dt = _filter_data_for_visible_blocks(dt, filtered_ul)
    else:
        filtered_ul = ul
        filtered_dt = dt
    return {
        "id": str(row.get("dashboard_id") or ""),
        "kind": row.get("kind") or "",
        "title": row.get("title") or "",
        "ui_layout": filtered_ul,
        "data": filtered_dt,
        "updated_at": (
            row.get("updated_at").isoformat()
            if isinstance(row.get("updated_at"), datetime)
            else str(row.get("updated_at") or "")
        ),
        "access_role": "viewer",
        "access_scope": "public",
        "share_label": (row.get("label") or "").strip(),
        "allowed_block_ids": block_ids if block_ids else None,
    }


def _password_check(row: dict[str, Any], password: str | None) -> Literal["ok", "password_required", "invalid_password"]:
    stored = row.get("password_hash")
    if not stored:
        return "ok"
    if not (password or "").strip():
        return "password_required"
    th = str(row.get("token_hash") or "")
    if not th:
        return "invalid_password"
    if hash_share_password(th, password) != stored:
        return "invalid_password"
    return "ok"


def public_share_list(
    actor_user_id: uuid.UUID, tenant_id: int, dashboard_id: uuid.UUID
) -> list[dict[str, Any]]:
    if not dashboard_can_manage_members(actor_user_id, tenant_id, dashboard_id):
        return []
    with db.pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT id, label, block_ids, expires_at, revoked_at, created_at, password_hash
                FROM dashboard_public_share_tokens
                WHERE dashboard_id = %s AND tenant_id = %s
                ORDER BY created_at DESC
                """,
                (dashboard_id, tenant_id),
            )
            rows = cur.fetchall()
        conn.commit()
    return [_share_row_to_public(dict(r)) for r in rows]


def public_share_create(
    actor_user_id: uuid.UUID,
    tenant_id: int,
    dashboard_id: uuid.UUID,
    *,
    block_ids: list[str],
    label: str = "",
    expires_at: datetime | None = None,
    password: str | None = None,
) -> tuple[str, dict[str, Any]] | None:
    """Returns ``(raw_token, share_meta)`` once; raw token is never stored."""
    if not dashboard_can_manage_members(actor_user_id, tenant_id, dashboard_id):
        return None
    pw = (password or "").strip()
    if pw and len(pw) < 4:
        return None
    with db.pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT ui_layout FROM user_dashboards
                WHERE id = %s AND tenant_id = %s
                """,
                (dashboard_id, tenant_id),
            )
            row = cur.fetchone()
            if not row:
                conn.commit()
                return None
            ui_layout = row["ui_layout"] if isinstance(row["ui_layout"], dict) else {}
            valid = _layout_block_ids(ui_layout)
            cleaned = [str(x).strip() for x in block_ids if str(x).strip()]
            cleaned = [x for x in cleaned if x in valid]
            if block_ids and not cleaned:
                conn.commit()
                return None
            raw = secrets.token_urlsafe(32)
            th = hash_share_token(raw)
            pw_hash = hash_share_password(th, pw) if pw else None
            cur.execute(
                """
                INSERT INTO dashboard_public_share_tokens (
                  dashboard_id, tenant_id, token_hash, label, block_ids,
                  expires_at, created_by, password_hash
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id, label, block_ids, expires_at, revoked_at, created_at, password_hash
                """,
                (
                    dashboard_id,
                    tenant_id,
                    th,
                    (label or "").strip()[:200],
                    cleaned,
                    expires_at,
                    actor_user_id,
                    pw_hash,
                ),
            )
            inserted = cur.fetchone()
        conn.commit()
    if not inserted:
        return None
    meta = _share_row_to_public(dict(inserted))
    return raw, meta


def public_share_revoke(
    actor_user_id: uuid.UUID,
    tenant_id: int,
    dashboard_id: uuid.UUID,
    share_id: uuid.UUID,
) -> bool:
    if not dashboard_can_manage_members(actor_user_id, tenant_id, dashboard_id):
        return False
    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE dashboard_public_share_tokens
                SET revoked_at = now()
                WHERE id = %s AND dashboard_id = %s AND tenant_id = %s
                  AND revoked_at IS NULL
                """,
                (share_id, dashboard_id, tenant_id),
            )
            n = cur.rowcount
        conn.commit()
    return n > 0


def _resolve_share_row(raw_token: str) -> dict[str, Any] | None:
    th = hash_share_token(raw_token)
    with db.pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT s.id, s.dashboard_id, s.tenant_id, s.token_hash, s.block_ids, s.label,
                  s.expires_at, s.revoked_at, s.password_hash,
                  w.kind, w.title, w.ui_layout, w.data, w.updated_at
                FROM dashboard_public_share_tokens s
                INNER JOIN user_dashboards w
                  ON w.id = s.dashboard_id AND w.tenant_id = s.tenant_id
                WHERE s.token_hash = %s
                  AND s.revoked_at IS NULL
                  AND (s.expires_at IS NULL OR s.expires_at > now())
                """,
                (th,),
            )
            row = cur.fetchone()
        conn.commit()
    return dict(row) if row else None


def public_share_get_dashboard(
    raw_token: str, *, password: str | None = None
) -> PublicShareViewResult:
    row = _resolve_share_row(raw_token)
    if not row:
        return PublicShareViewResult("not_found")
    label = (row.get("label") or "").strip()
    gate = _password_check(row, password)
    if gate == "password_required":
        return PublicShareViewResult("password_required", share_label=label)
    if gate == "invalid_password":
        return PublicShareViewResult("invalid_password", share_label=label)
    return PublicShareViewResult("ok", dashboard=_dashboard_payload_from_row(row), share_label=label)


def public_share_file_access(
    raw_token: str, file_id: uuid.UUID, *, password: str | None = None
) -> dict[str, Any] | None:
    """Return file metadata when token grants read access to that file: reference."""
    row = _resolve_share_row(raw_token)
    if not row:
        return None
    if _password_check(row, password) != "ok":
        return None
    dash_id = row.get("dashboard_id")
    tenant_id = row.get("tenant_id")
    if not isinstance(dash_id, uuid.UUID):
        dash_id = uuid.UUID(str(dash_id))
    raw_ids = row.get("block_ids")
    block_ids = [str(x).strip() for x in raw_ids] if isinstance(raw_ids, list) else []
    block_ids = [x for x in block_ids if x]
    ul = row.get("ui_layout") if isinstance(row.get("ui_layout"), dict) else {}
    dt = row.get("data") if isinstance(row.get("data"), dict) else {}
    if block_ids:
        allowed = frozenset(block_ids)
        filtered_ul = _filter_ui_layout(ul, allowed)
        filtered_dt = _filter_data_for_visible_blocks(dt, filtered_ul)
    else:
        filtered_dt = dt
    visible_files = file_ids_in_value(filtered_dt)
    if str(file_id) not in visible_files:
        return None
    with db.pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT id, dashboard_id, storage_relpath, content_type,
                       size_bytes, original_name
                FROM user_attachments
                WHERE id = %s AND tenant_id = %s AND dashboard_id = %s
                """,
                (file_id, tenant_id, dash_id),
            )
            frow = cur.fetchone()
        conn.commit()
    return dict(frow) if frow else None
