"""CRUD for user_collections, collection_items, user_attachments."""

from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Any, Protocol

from psycopg.rows import dict_row
from psycopg.types.json import Json

_SLUG_RE = re.compile(r"^[a-z][a-z0-9._-]{0,95}$")


class CollectionsDbDependencies(Protocol):
    def pool(self) -> Any: ...


_deps: CollectionsDbDependencies | None = None


def register_collections_db_dependencies(deps: CollectionsDbDependencies) -> None:
    global _deps
    _deps = deps


class _DbPort:
    def pool(self) -> Any:
        if _deps is None:
            raise RuntimeError("collections db dependencies not registered")
        return _deps.pool()


db = _DbPort()


def normalize_slug(raw: str) -> str | None:
    s = (raw or "").strip().lower()
    if not s or not _SLUG_RE.match(s):
        return None
    return s


def collection_ensure(
    *,
    tenant_id: int,
    owner_user_id: uuid.UUID,
    slug: str,
    title: str = "",
    schema_hint: str | None = None,
) -> dict[str, Any]:
    norm = normalize_slug(slug)
    if norm is None:
        raise ValueError("invalid collection slug")
    with db.pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                INSERT INTO user_collections (tenant_id, owner_user_id, slug, title, schema_hint)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (owner_user_id, slug) DO UPDATE SET
                  title = CASE WHEN EXCLUDED.title <> '' THEN EXCLUDED.title ELSE user_collections.title END,
                  schema_hint = COALESCE(EXCLUDED.schema_hint, user_collections.schema_hint),
                  updated_at = now()
                RETURNING id, tenant_id, owner_user_id, slug, title, schema_hint, metadata,
                          created_at, updated_at
                """,
                (tenant_id, owner_user_id, norm, (title or norm).strip()[:500], schema_hint),
            )
            row = cur.fetchone()
        conn.commit()
    return _collection_row(row)


def collection_get(
    owner_user_id: uuid.UUID,
    slug: str,
) -> dict[str, Any] | None:
    norm = normalize_slug(slug)
    if norm is None:
        return None
    with db.pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT id, tenant_id, owner_user_id, slug, title, schema_hint, metadata,
                       created_at, updated_at
                FROM user_collections
                WHERE owner_user_id = %s AND slug = %s
                """,
                (owner_user_id, norm),
            )
            row = cur.fetchone()
        conn.commit()
    return _collection_row(row) if row else None


def collection_get_by_id(collection_id: uuid.UUID) -> dict[str, Any] | None:
    with db.pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT id, tenant_id, owner_user_id, slug, title, schema_hint, metadata,
                       created_at, updated_at
                FROM user_collections WHERE id = %s
                """,
                (collection_id,),
            )
            row = cur.fetchone()
        conn.commit()
    return _collection_row(row) if row else None


def collection_list(owner_user_id: uuid.UUID, *, limit: int = 100) -> list[dict[str, Any]]:
    lim = max(1, min(int(limit), 200))
    with db.pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT id, slug, title, schema_hint, updated_at
                FROM user_collections
                WHERE owner_user_id = %s
                ORDER BY slug
                LIMIT %s
                """,
                (owner_user_id, lim),
            )
            rows = cur.fetchall()
        conn.commit()
    return [
        {
            "id": str(r["id"]),
            "slug": r["slug"],
            "title": r["title"],
            "schema_hint": r.get("schema_hint"),
            "updated_at": r["updated_at"].isoformat() if r.get("updated_at") else None,
        }
        for r in rows
    ]


def collection_metadata_patch(
    owner_user_id: uuid.UUID,
    slug: str,
    patches: dict[str, Any],
) -> dict[str, Any] | None:
    col = collection_get(owner_user_id, slug)
    if col is None:
        return None
    meta = dict(col.get("metadata") or {})
    meta.update(patches)
    with db.pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                UPDATE user_collections
                SET metadata = %s, updated_at = now()
                WHERE id = %s AND owner_user_id = %s
                RETURNING id, tenant_id, owner_user_id, slug, title, schema_hint, metadata,
                          created_at, updated_at
                """,
                (Json(meta), uuid.UUID(str(col["id"])), owner_user_id),
            )
            row = cur.fetchone()
        conn.commit()
    return _collection_row(row) if row else None


def items_list(
    collection_id: uuid.UUID,
    list_key: str,
    *,
    limit: int = 2000,
) -> list[dict[str, Any]]:
    lk = (list_key or "items").strip() or "items"
    with db.pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT row_id, data, sort_order
                FROM collection_items
                WHERE collection_id = %s AND list_key = %s
                ORDER BY sort_order ASC, created_at ASC
                LIMIT %s
                """,
                (collection_id, lk, max(1, min(limit, 2000))),
            )
            rows = cur.fetchall()
        conn.commit()
    out: list[dict[str, Any]] = []
    for r in rows:
        data = r["data"] if isinstance(r["data"], dict) else {}
        row = dict(data)
        rid = str(r.get("row_id") or row.get("id") or "").strip()
        if rid and not row.get("id"):
            row["id"] = rid
        out.append(row)
    return out


def items_append(
    collection_id: uuid.UUID,
    list_key: str,
    rows: list[dict[str, Any]],
    *,
    start_sort: int | None = None,
) -> list[dict[str, Any]]:
    lk = (list_key or "items").strip() or "items"
    added: list[dict[str, Any]] = []
    with db.pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            if start_sort is None:
                cur.execute(
                    """
                    SELECT COALESCE(MAX(sort_order), -1) + 1
                    FROM collection_items
                    WHERE collection_id = %s AND list_key = %s
                    """,
                    (collection_id, lk),
                )
                base = int(cur.fetchone()[0])
            else:
                base = int(start_sort)
            for i, entry in enumerate(rows):
                if not isinstance(entry, dict):
                    continue
                data = dict(entry)
                rid = str(data.get("id") or "").strip() or f"r_{uuid.uuid4().hex[:12]}"
                data["id"] = rid
                cur.execute(
                    """
                    INSERT INTO collection_items (collection_id, list_key, row_id, sort_order, data)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (collection_id, list_key, row_id) DO UPDATE SET
                      data = EXCLUDED.data,
                      sort_order = EXCLUDED.sort_order,
                      updated_at = now()
                    """,
                    (collection_id, lk, rid, base + i, Json(data)),
                )
                added.append(data)
        conn.commit()
    return added


def item_update(
    collection_id: uuid.UUID,
    list_key: str,
    row_id: str,
    patch: dict[str, Any],
) -> dict[str, Any] | None:
    lk = (list_key or "items").strip() or "items"
    rid = (row_id or "").strip()
    if not rid:
        return None
    with db.pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT data FROM collection_items
                WHERE collection_id = %s AND list_key = %s AND row_id = %s
                """,
                (collection_id, lk, rid),
            )
            row = cur.fetchone()
            if not row:
                return None
            data = dict(row[0]) if isinstance(row[0], dict) else {}
            data.update(patch)
            data["id"] = rid
            cur.execute(
                """
                UPDATE collection_items SET data = %s, updated_at = now()
                WHERE collection_id = %s AND list_key = %s AND row_id = %s
                """,
                (Json(data), collection_id, lk, rid),
            )
        conn.commit()
    return data


def item_delete(collection_id: uuid.UUID, list_key: str, row_id: str) -> bool:
    lk = (list_key or "items").strip() or "items"
    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM collection_items
                WHERE collection_id = %s AND list_key = %s AND row_id = %s
                """,
                (collection_id, lk, (row_id or "").strip()),
            )
            n = cur.rowcount
        conn.commit()
    return n > 0


def attachment_insert(
    *,
    tenant_id: int,
    owner_user_id: uuid.UUID,
    storage_relpath: str,
    content_type: str,
    size_bytes: int,
    original_name: str,
    collection_id: uuid.UUID | None = None,
    collection_item_id: uuid.UUID | None = None,
    dashboard_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    with db.pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                INSERT INTO user_attachments (
                  tenant_id, owner_user_id, collection_id, collection_item_id,
                  dashboard_id, storage_relpath, content_type, size_bytes, original_name
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id, content_type, size_bytes, original_name, created_at
                """,
                (
                    tenant_id,
                    owner_user_id,
                    collection_id,
                    collection_item_id,
                    dashboard_id,
                    storage_relpath,
                    content_type,
                    size_bytes,
                    (original_name or "")[:500],
                ),
            )
            row = cur.fetchone()
        conn.commit()
    if not row:
        raise RuntimeError("attachment insert failed")
    fid = str(row["id"])
    return {
        "id": fid,
        "gallery_ref": f"file:{fid}",
        "content_type": row["content_type"],
        "size_bytes": int(row["size_bytes"]),
        "original_name": row["original_name"],
    }


def _collection_row(row: dict[str, Any] | None) -> dict[str, Any]:
    if not row:
        return {}
    return {
        "id": str(row["id"]),
        "tenant_id": int(row.get("tenant_id") or 0),
        "owner_user_id": str(row.get("owner_user_id") or ""),
        "slug": row["slug"],
        "title": row.get("title") or "",
        "schema_hint": row.get("schema_hint"),
        "metadata": row.get("metadata") if isinstance(row.get("metadata"), dict) else {},
        "created_at": row["created_at"].isoformat() if isinstance(row.get("created_at"), datetime) else None,
        "updated_at": row["updated_at"].isoformat() if isinstance(row.get("updated_at"), datetime) else None,
    }
