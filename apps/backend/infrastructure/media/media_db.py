"""Metadata rows for media library uploads (bytes on disk under ``media_upload_dir()``)."""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any

from psycopg.rows import dict_row

from apps.backend.infrastructure.db import db


def media_tables_exist() -> bool:
    try:
        with db.pool().connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT to_regclass('public.media_items')")
                row = cur.fetchone()
        return bool(row and row[0])
    except Exception:
        return False


def media_share_tables_exist() -> bool:
    try:
        with db.pool().connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT to_regclass('public.media_share_grants')")
                row = cur.fetchone()
        return bool(row and row[0])
    except Exception:
        return False


def _row(r: dict[str, Any]) -> dict[str, Any]:
    mid = r.get("id")
    wid = str(mid) if isinstance(mid, uuid.UUID) else str(mid or "")
    ca = r.get("created_at")
    ua = r.get("updated_at")
    tags = r.get("tags")
    if tags is None:
        tag_list: list[str] = []
    elif isinstance(tags, list):
        tag_list = [str(x) for x in tags]
    else:
        tag_list = []
    meta = r.get("metadata")
    if isinstance(meta, dict):
        metadata = meta
    elif isinstance(meta, str) and meta.strip():
        try:
            metadata = json.loads(meta)
        except json.JSONDecodeError:
            metadata = {}
    else:
        metadata = {}
    dash = r.get("dashboard_id")
    return {
        "id": wid,
        "tenant_id": int(r.get("tenant_id") or 0),
        "owner_user_id": str(r.get("owner_user_id") or ""),
        "dashboard_id": str(dash) if dash else None,
        "source_kind": str(r.get("source_kind") or ""),
        "storage_relpath": r.get("storage_relpath") or "",
        "content_type": r.get("content_type") or "",
        "size_bytes": int(r.get("size_bytes") or 0),
        "original_name": r.get("original_name") or "",
        "external_url": r.get("external_url") or "",
        "embed_provider": r.get("embed_provider") or "",
        "title": r.get("title") or "",
        "artist": r.get("artist") or "",
        "album": r.get("album") or "",
        "duration_sec": int(r["duration_sec"]) if r.get("duration_sec") is not None else None,
        "cover_url": r.get("cover_url") or "",
        "license": r.get("license"),
        "license_note": r.get("license_note") or "",
        "tags": tag_list,
        "metadata": metadata,
        "created_at": ca.isoformat() if isinstance(ca, datetime) else str(ca or ""),
        "updated_at": ua.isoformat() if isinstance(ua, datetime) else str(ua or ""),
    }


def user_upload_bytes_used(*, user_id: uuid.UUID, tenant_id: int) -> int:
    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COALESCE(SUM(size_bytes), 0)
                FROM media_items
                WHERE tenant_id = %s AND owner_user_id = %s
                  AND source_kind = 'upload' AND deleted_at IS NULL
                """,
                (tenant_id, user_id),
            )
            row = cur.fetchone()
    if not row:
        return 0
    return int(row[0] or 0)


def item_insert_upload(
    *,
    tenant_id: int,
    owner_user_id: uuid.UUID,
    dashboard_id: uuid.UUID | None,
    storage_relpath: str,
    content_type: str,
    size_bytes: int,
    original_name: str,
    title: str = "",
    artist: str = "",
) -> dict[str, Any]:
    with db.pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                INSERT INTO media_items (
                  tenant_id, owner_user_id, dashboard_id, source_kind,
                  storage_relpath, content_type, size_bytes, original_name,
                  title, artist
                )
                VALUES (%s, %s, %s, 'upload', %s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (
                    tenant_id,
                    owner_user_id,
                    dashboard_id,
                    storage_relpath,
                    content_type,
                    size_bytes,
                    (original_name or "")[:500],
                    (title or "")[:500],
                    (artist or "")[:500],
                ),
            )
            row = cur.fetchone()
        conn.commit()
    if not row:
        raise RuntimeError("media_items insert failed")
    return _row(dict(row))


def item_insert_embed(
    *,
    tenant_id: int,
    owner_user_id: uuid.UUID,
    dashboard_id: uuid.UUID | None,
    external_url: str,
    embed_provider: str,
    title: str = "",
    artist: str = "",
) -> dict[str, Any]:
    with db.pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                INSERT INTO media_items (
                  tenant_id, owner_user_id, dashboard_id, source_kind,
                  external_url, embed_provider, title, artist
                )
                VALUES (%s, %s, %s, 'embed', %s, %s, %s, %s)
                RETURNING *
                """,
                (
                    tenant_id,
                    owner_user_id,
                    dashboard_id,
                    external_url[:2048],
                    embed_provider[:64],
                    (title or "")[:500],
                    (artist or "")[:500],
                ),
            )
            row = cur.fetchone()
        conn.commit()
    if not row:
        raise RuntimeError("media_items embed insert failed")
    return _row(dict(row))


def item_insert_external_link(
    *,
    tenant_id: int,
    owner_user_id: uuid.UUID,
    dashboard_id: uuid.UUID | None,
    external_url: str,
    embed_provider: str,
    title: str = "",
    artist: str = "",
) -> dict[str, Any]:
    with db.pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                INSERT INTO media_items (
                  tenant_id, owner_user_id, dashboard_id, source_kind,
                  external_url, embed_provider, title, artist
                )
                VALUES (%s, %s, %s, 'external_link', %s, %s, %s, %s)
                RETURNING *
                """,
                (
                    tenant_id,
                    owner_user_id,
                    dashboard_id,
                    external_url[:2048],
                    embed_provider[:64],
                    (title or "")[:500],
                    (artist or "")[:500],
                ),
            )
            row = cur.fetchone()
        conn.commit()
    if not row:
        raise RuntimeError("media_items external_link insert failed")
    return _row(dict(row))


def item_get_owned(
    item_id: uuid.UUID, user_id: uuid.UUID, tenant_id: int
) -> dict[str, Any] | None:
    with db.pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT *
                FROM media_items
                WHERE id = %s AND tenant_id = %s AND owner_user_id = %s
                  AND deleted_at IS NULL
                """,
                (item_id, tenant_id, user_id),
            )
            row = cur.fetchone()
        conn.commit()
    return _row(dict(row)) if row else None


def item_list_owned(
    *,
    user_id: uuid.UUID,
    tenant_id: int,
    source_kind: str | None = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    lim = max(1, min(int(limit), 500))
    params: list[Any] = [tenant_id, user_id]
    kind_sql = ""
    if source_kind:
        kind_sql = " AND source_kind = %s"
        params.append(source_kind.strip())
    params.append(lim)
    with db.pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                f"""
                SELECT *
                FROM media_items
                WHERE tenant_id = %s AND owner_user_id = %s
                  AND deleted_at IS NULL
                  {kind_sql}
                ORDER BY created_at DESC
                LIMIT %s
                """,
                tuple(params),
            )
            rows = cur.fetchall()
        conn.commit()
    return [_row(dict(r)) for r in rows]


def item_soft_delete(item_id: uuid.UUID, user_id: uuid.UUID, tenant_id: int) -> str | None:
    """Soft-delete upload; returns ``storage_relpath`` when an upload row was removed."""
    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE media_items
                SET deleted_at = now(), updated_at = now()
                WHERE id = %s AND tenant_id = %s AND owner_user_id = %s
                  AND deleted_at IS NULL
                RETURNING storage_relpath, source_kind
                """,
                (item_id, tenant_id, user_id),
            )
            row = cur.fetchone()
        conn.commit()
    if not row:
        return None
    relpath, kind = row[0], row[1]
    if kind == "upload" and relpath:
        return str(relpath)
    return ""


def item_update_license(
    *,
    item_id: uuid.UUID,
    owner_user_id: uuid.UUID,
    tenant_id: int,
    license: str,
    license_note: str = "",
) -> dict[str, Any] | None:
    from apps.backend.infrastructure.media.media_policy import normalize_media_license

    lic = normalize_media_license(license)
    if not lic:
        return None
    with db.pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                UPDATE media_items
                SET license = %s,
                    license_note = %s,
                    updated_at = now()
                WHERE id = %s AND tenant_id = %s AND owner_user_id = %s
                  AND source_kind = 'upload' AND deleted_at IS NULL
                RETURNING *
                """,
                (lic, (license_note or "")[:2000], item_id, tenant_id, owner_user_id),
            )
            row = cur.fetchone()
        conn.commit()
    return _row(dict(row)) if row else None


def item_get_with_access(
    item_id: uuid.UUID, user_id: uuid.UUID, tenant_id: int
) -> tuple[dict[str, Any] | None, str | None, bool]:
    """Return (row, share_permission, is_owner). ``share_permission`` is set for viewers."""
    owned = item_get_owned(item_id, user_id, tenant_id)
    if owned:
        return owned, None, True
    if not media_share_tables_exist():
        return None, None, False
    with db.pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT m.*, g.permission AS share_permission
                FROM media_items m
                INNER JOIN media_share_grants g
                  ON g.media_item_id = m.id AND g.viewer_user_id = %s AND g.tenant_id = %s
                WHERE m.id = %s AND m.tenant_id = %s AND m.deleted_at IS NULL
                  AND m.source_kind = 'upload'
                  AND (g.expires_at IS NULL OR g.expires_at > now())
                """,
                (user_id, tenant_id, item_id, tenant_id),
            )
            row = cur.fetchone()
        conn.commit()
    if not row:
        return None, None, False
    d = dict(row)
    perm = str(d.pop("share_permission", "") or "play")
    return _row(d), perm, False


def item_list_accessible(
    *,
    user_id: uuid.UUID,
    tenant_id: int,
    source_kind: str | None = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    owned = item_list_owned(
        user_id=user_id, tenant_id=tenant_id, source_kind=source_kind, limit=limit
    )
    for r in owned:
        r["access"] = "owner"
    if not media_share_tables_exist():
        return owned
    lim = max(1, min(int(limit), 500))
    params: list[Any] = [user_id, tenant_id, tenant_id, user_id]
    kind_sql = ""
    if source_kind:
        kind_sql = " AND m.source_kind = %s"
        params.append(source_kind.strip())
    params.append(lim)
    with db.pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                f"""
                SELECT m.*, g.permission AS share_permission
                FROM media_items m
                INNER JOIN media_share_grants g
                  ON g.media_item_id = m.id AND g.viewer_user_id = %s AND g.tenant_id = %s
                WHERE m.tenant_id = %s AND m.owner_user_id <> %s
                  AND m.deleted_at IS NULL
                  AND (g.expires_at IS NULL OR g.expires_at > now())
                  {kind_sql}
                ORDER BY g.created_at DESC
                LIMIT %s
                """,
                tuple(params),
            )
            rows = cur.fetchall()
        conn.commit()
    shared: list[dict[str, Any]] = []
    owned_ids = {r["id"] for r in owned}
    for r in rows:
        d = dict(r)
        perm = str(d.pop("share_permission", "") or "play")
        item = _row(d)
        if item["id"] in owned_ids:
            continue
        item["access"] = "shared"
        item["share_permission"] = perm
        shared.append(item)
    return owned + shared


def _grant_row(r: dict[str, Any]) -> dict[str, Any]:
    ca = r.get("created_at")
    exp = r.get("expires_at")
    return {
        "id": str(r.get("id") or ""),
        "media_item_id": str(r.get("media_item_id") or ""),
        "viewer_user_id": str(r.get("viewer_user_id") or ""),
        "viewer_email": (r.get("viewer_email") or "").strip(),
        "permission": str(r.get("permission") or "play"),
        "created_at": ca.isoformat() if isinstance(ca, datetime) else str(ca or ""),
        "expires_at": exp.isoformat() if isinstance(exp, datetime) else None,
    }


def share_grants_list(
    *,
    owner_user_id: uuid.UUID,
    tenant_id: int,
    media_item_id: uuid.UUID | None = None,
) -> list[dict[str, Any]]:
    if not media_share_tables_exist():
        return []
    params: list[Any] = [tenant_id, owner_user_id]
    item_sql = ""
    if media_item_id is not None:
        item_sql = " AND g.media_item_id = %s"
        params.append(media_item_id)
    with db.pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                f"""
                SELECT g.*, u.email AS viewer_email
                FROM media_share_grants g
                LEFT JOIN users u ON u.id = g.viewer_user_id
                WHERE g.tenant_id = %s AND g.owner_user_id = %s
                  {item_sql}
                ORDER BY g.created_at DESC
                """,
                tuple(params),
            )
            rows = cur.fetchall()
        conn.commit()
    return [_grant_row(dict(r)) for r in rows]


def share_grant_upsert(
    *,
    owner_user_id: uuid.UUID,
    tenant_id: int,
    media_item_id: uuid.UUID,
    viewer_user_id: uuid.UUID,
    permission: str = "play",
) -> dict[str, Any] | None:
    if not media_share_tables_exist():
        return None
    if viewer_user_id == owner_user_id:
        return None
    if db.user_tenant_id(viewer_user_id) != tenant_id:
        return None
    perm = str(permission or "play").strip().lower()
    if perm not in ("play", "play_and_download"):
        return None
    item = item_get_owned(media_item_id, owner_user_id, tenant_id)
    if not item or item.get("source_kind") != "upload":
        return None
    from apps.backend.infrastructure.media.media_policy import item_is_shareable

    if not item_is_shareable(item):
        return None
    with db.pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                INSERT INTO media_share_grants (
                  tenant_id, media_item_id, owner_user_id, viewer_user_id, permission
                )
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (media_item_id, viewer_user_id)
                DO UPDATE SET permission = EXCLUDED.permission
                RETURNING *
                """,
                (tenant_id, media_item_id, owner_user_id, viewer_user_id, perm),
            )
            row = cur.fetchone()
            if row:
                d = dict(row)
                cur.execute("SELECT email FROM users WHERE id = %s", (viewer_user_id,))
                em = cur.fetchone()
                if em:
                    d["viewer_email"] = em[0]
                row = d
        conn.commit()
    return _grant_row(dict(row)) if row else None


def share_grant_delete(
    *,
    owner_user_id: uuid.UUID,
    tenant_id: int,
    grant_id: uuid.UUID,
) -> bool:
    if not media_share_tables_exist():
        return False
    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM media_share_grants
                WHERE id = %s AND tenant_id = %s AND owner_user_id = %s
                """,
                (grant_id, tenant_id, owner_user_id),
            )
            n = cur.rowcount
        conn.commit()
    return n > 0
