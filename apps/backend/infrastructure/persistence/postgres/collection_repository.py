"""Postgres-backed repositories for collections."""

from __future__ import annotations

import uuid
from typing import Any

from psycopg.rows import dict_row
from psycopg.types.json import Json

from apps.backend.domain.collections.entities import Collection, CollectionItem
from apps.backend.domain.collections.repositories import (
    AttachmentRepository,
    CollectionItemRepository,
    CollectionRepository,
)
from apps.backend.domain.collections.value_objects import CollectionSlug, DataPath
from apps.backend.infrastructure.db import db
from apps.backend.infrastructure.persistence.postgres.collection_rows import (
    attachment_row,
    collection_from_row,
    collection_row,
    uuid_or_none,
)


class PostgresCollectionPersistenceAdapter:
    """Postgres implementation of the collections persistence ports."""

    def collection_ensure(
        self,
        *,
        tenant_id: int,
        owner_user_id: uuid.UUID,
        slug: str,
        title: str = "",
        schema_hint: str | None = None,
    ) -> dict[str, Any]:
        norm = CollectionSlug.require(slug)
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
                    (tenant_id, owner_user_id, str(norm), (title or str(norm)).strip()[:500], schema_hint),
                )
                row = cur.fetchone()
            conn.commit()
        return collection_row(row)

    def collection_get(self, owner_user_id: uuid.UUID, slug: str) -> dict[str, Any] | None:
        norm = CollectionSlug.parse(slug)
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
                    (owner_user_id, str(norm)),
                )
                row = cur.fetchone()
            conn.commit()
        return collection_row(row) if row else None

    def collection_get_by_id(self, collection_id: uuid.UUID) -> dict[str, Any] | None:
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
        return collection_row(row) if row else None

    def collection_list(self, owner_user_id: uuid.UUID, *, limit: int = 100) -> list[dict[str, Any]]:
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
                "id": str(row["id"]),
                "slug": row["slug"],
                "title": row["title"],
                "schema_hint": row.get("schema_hint"),
                "updated_at": row["updated_at"].isoformat() if row.get("updated_at") else None,
            }
            for row in rows
        ]

    def collection_metadata_patch(
        self,
        owner_user_id: uuid.UUID,
        slug: str,
        patches: dict[str, Any],
    ) -> dict[str, Any] | None:
        collection = self.collection_get(owner_user_id, slug)
        if collection is None:
            return None
        meta = dict(collection.get("metadata") or {})
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
                    (Json(meta), uuid.UUID(str(collection["id"])), owner_user_id),
                )
                row = cur.fetchone()
            conn.commit()
        return collection_row(row) if row else None

    def items_list(
        self,
        collection_id: uuid.UUID,
        list_key: str,
        *,
        limit: int = 2000,
    ) -> list[dict[str, Any]]:
        key = (list_key or "items").strip() or "items"
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
                    (collection_id, key, max(1, min(limit, 2000))),
                )
                rows = cur.fetchall()
            conn.commit()
        out: list[dict[str, Any]] = []
        for row in rows:
            data = row["data"] if isinstance(row["data"], dict) else {}
            item = dict(data)
            row_id = str(row.get("row_id") or item.get("id") or "").strip()
            if row_id and not item.get("id"):
                item["id"] = row_id
            out.append(item)
        return out

    def items_append(
        self,
        collection_id: uuid.UUID,
        list_key: str,
        rows: list[dict[str, Any]],
        *,
        start_sort: int | None = None,
    ) -> list[dict[str, Any]]:
        key = (list_key or "items").strip() or "items"
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
                        (collection_id, key),
                    )
                    base = int(cur.fetchone()[0])
                else:
                    base = int(start_sort)
                for i, entry in enumerate(rows):
                    if not isinstance(entry, dict):
                        continue
                    data = dict(entry)
                    row_id = str(data.get("id") or "").strip() or f"r_{uuid.uuid4().hex[:12]}"
                    data["id"] = row_id
                    cur.execute(
                        """
                        INSERT INTO collection_items (collection_id, list_key, row_id, sort_order, data)
                        VALUES (%s, %s, %s, %s, %s)
                        ON CONFLICT (collection_id, list_key, row_id) DO UPDATE SET
                          data = EXCLUDED.data,
                          sort_order = EXCLUDED.sort_order,
                          updated_at = now()
                        """,
                        (collection_id, key, row_id, base + i, Json(data)),
                    )
                    added.append(data)
            conn.commit()
        return added

    def item_update(
        self,
        collection_id: uuid.UUID,
        list_key: str,
        row_id: str,
        patch: dict[str, Any],
    ) -> dict[str, Any] | None:
        key = (list_key or "items").strip() or "items"
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
                    (collection_id, key, rid),
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
                    (Json(data), collection_id, key, rid),
                )
            conn.commit()
        return data

    def item_delete(self, collection_id: uuid.UUID, list_key: str, row_id: str) -> bool:
        key = (list_key or "items").strip() or "items"
        with db.pool().connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    DELETE FROM collection_items
                    WHERE collection_id = %s AND list_key = %s AND row_id = %s
                    """,
                    (collection_id, key, (row_id or "").strip()),
                )
                deleted_count = cur.rowcount
            conn.commit()
        return deleted_count > 0

    def replace_items(
        self,
        collection_id: uuid.UUID,
        list_key: str,
        rows: list[dict[str, Any]],
    ) -> None:
        key = (list_key or "items").strip() or "items"
        with db.pool().connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM collection_items WHERE collection_id = %s AND list_key = %s",
                    (collection_id, key),
                )
            conn.commit()
        if rows:
            self.items_append(collection_id, key, rows)

    def attachment_insert(
        self,
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
        file_id = str(row["id"])
        return {
            "id": file_id,
            "gallery_ref": f"file:{file_id}",
            "content_type": row["content_type"],
            "size_bytes": int(row["size_bytes"]),
            "original_name": row["original_name"],
        }

    def attachment_get_with_access(
        self,
        file_id: uuid.UUID,
        user_id: uuid.UUID,
        tenant_id: int,
    ) -> dict[str, Any] | None:
        with db.pool().connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    SELECT a.id, a.owner_user_id, a.collection_id, a.storage_relpath,
                           a.content_type, a.size_bytes, a.original_name, a.created_at
                    FROM user_attachments a
                    WHERE a.id = %s AND a.tenant_id = %s
                      AND (
                        a.owner_user_id = %s
                        OR EXISTS (
                          SELECT 1 FROM share_permissions sp
                          JOIN user_collections uc ON uc.owner_user_id = sp.owner_user_id
                            AND uc.id = a.collection_id
                          WHERE sp.grantee_user_id = %s
                            AND sp.owner_user_id = a.owner_user_id
                            AND sp.resource_type = 'collection'
                            AND sp.is_allowed = TRUE
                            AND sp.revoked_at IS NULL
                            AND lower(sp.resource_identifier) = uc.slug
                        )
                        OR EXISTS (
                          SELECT 1 FROM user_dashboards w
                          WHERE w.id = a.dashboard_id AND w.tenant_id = a.tenant_id
                            AND (
                              w.owner_user_id = %s
                              OR EXISTS (
                                SELECT 1 FROM dashboard_members m
                                WHERE m.dashboard_id = w.id AND m.user_id = %s
                              )
                              OR EXISTS (
                                SELECT 1 FROM dashboard_block_share_grants g
                                WHERE g.dashboard_id = w.id
                                  AND g.viewer_user_id = %s
                                  AND g.tenant_id = w.tenant_id
                              )
                              OR EXISTS (
                                SELECT 1 FROM share_permissions sp
                                WHERE sp.grantee_user_id = %s
                                  AND sp.owner_user_id = w.owner_user_id
                                  AND sp.resource_type = 'dashboard'
                                  AND sp.is_allowed = TRUE
                                  AND sp.revoked_at IS NULL
                                  AND lower(sp.resource_identifier) = lower(w.id::text)
                              )
                            )
                        )
                      )
                    """,
                    (file_id, tenant_id, user_id, user_id, user_id, user_id, user_id, user_id),
                )
                row = cur.fetchone()
            conn.commit()
        return attachment_row(dict(row)) if row else None

    def attachment_delete_with_access(
        self,
        file_id: uuid.UUID,
        user_id: uuid.UUID,
        tenant_id: int,
    ) -> str | None:
        with db.pool().connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    DELETE FROM user_attachments
                    WHERE id = %s AND tenant_id = %s AND owner_user_id = %s
                    RETURNING storage_relpath
                    """,
                    (file_id, tenant_id, user_id),
                )
                row = cur.fetchone()
            conn.commit()
        if not row or row[0] is None:
            return None
        return str(row[0])


_persistence = PostgresCollectionPersistenceAdapter()


class PostgresCollectionRepository(CollectionRepository):
    def ensure(
        self,
        *,
        tenant_id: int,
        owner_user_id: uuid.UUID,
        slug: CollectionSlug,
        title: str = "",
        schema_hint: str | None = None,
    ) -> Collection:
        row = _persistence.collection_ensure(
            tenant_id=tenant_id,
            owner_user_id=owner_user_id,
            slug=str(slug),
            title=title,
            schema_hint=schema_hint,
        )
        collection = collection_from_row(row)
        if collection is None:
            raise RuntimeError("collection ensure returned invalid row")
        return collection

    def get_by_slug(
        self,
        owner_user_id: uuid.UUID,
        slug: CollectionSlug,
    ) -> Collection | None:
        return collection_from_row(_persistence.collection_get(owner_user_id, str(slug)))

    def list_for_owner(self, owner_user_id: uuid.UUID, *, limit: int = 100) -> list[Collection]:
        rows = _persistence.collection_list(owner_user_id, limit=limit)
        out: list[Collection] = []
        for row in rows:
            slug = CollectionSlug.parse(str(row.get("slug") or ""))
            if slug is None:
                continue
            out.append(
                Collection(
                    id=uuid_or_none(row.get("id")),
                    tenant_id=0,
                    owner_user_id=owner_user_id,
                    slug=slug,
                    title=str(row.get("title") or str(slug)),
                    schema_hint=row.get("schema_hint") if isinstance(row.get("schema_hint"), str) else None,
                    metadata={},
                )
            )
        return out

    def patch_metadata(
        self,
        owner_user_id: uuid.UUID,
        slug: CollectionSlug,
        patch: dict[str, Any],
    ) -> Collection | None:
        return collection_from_row(
            _persistence.collection_metadata_patch(owner_user_id, str(slug), patch)
        )


class PostgresCollectionItemRepository(CollectionItemRepository):
    def list_items(
        self,
        collection_id: uuid.UUID,
        list_key: DataPath,
        *,
        limit: int = 2000,
    ) -> list[CollectionItem]:
        rows = _persistence.items_list(collection_id, str(list_key), limit=limit)
        return [CollectionItem.from_row_data(row, list_key=str(list_key), sort_order=i) for i, row in enumerate(rows)]

    def append_items(
        self,
        collection_id: uuid.UUID,
        list_key: DataPath,
        rows: list[dict[str, Any]],
    ) -> list[CollectionItem]:
        added = _persistence.items_append(collection_id, str(list_key), rows)
        return [CollectionItem.from_row_data(row, list_key=str(list_key), sort_order=i) for i, row in enumerate(added)]

    def update_item(
        self,
        collection_id: uuid.UUID,
        list_key: DataPath,
        row_id: str,
        patch: dict[str, Any],
    ) -> CollectionItem | None:
        row = _persistence.item_update(collection_id, str(list_key), row_id, patch)
        return CollectionItem.from_row_data(row, list_key=str(list_key)) if row else None

    def delete_item(self, collection_id: uuid.UUID, list_key: DataPath, row_id: str) -> bool:
        return _persistence.item_delete(collection_id, str(list_key), row_id)

    def replace_items(
        self,
        collection_id: uuid.UUID,
        list_key: DataPath,
        rows: list[dict[str, Any]],
    ) -> None:
        _persistence.replace_items(collection_id, str(list_key), rows)


class PostgresAttachmentRepository(AttachmentRepository):
    def insert_upload(
        self,
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
        return _persistence.attachment_insert(
            tenant_id=tenant_id,
            owner_user_id=owner_user_id,
            storage_relpath=storage_relpath,
            content_type=content_type,
            size_bytes=size_bytes,
            original_name=original_name,
            collection_id=collection_id,
            collection_item_id=collection_item_id,
            dashboard_id=dashboard_id,
        )

    def get_with_access(
        self,
        file_id: uuid.UUID,
        user_id: uuid.UUID,
        tenant_id: int,
    ) -> Any | None:
        return _persistence.attachment_get_with_access(file_id, user_id, tenant_id)

    def delete_with_access(
        self,
        file_id: uuid.UUID,
        user_id: uuid.UUID,
        tenant_id: int,
    ) -> str | None:
        return _persistence.attachment_delete_with_access(file_id, user_id, tenant_id)
