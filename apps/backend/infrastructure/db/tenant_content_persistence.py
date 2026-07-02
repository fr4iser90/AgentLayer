from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from psycopg.rows import dict_row
from psycopg.types.json import Json

from apps.backend.infrastructure.db.db import pool


def _content_select_columns() -> str:
    return """
        id, tenant_id, slug, title, body_md, status, source_type,
        disclaimer_level, target_profession_roles, target_departments,
        required_qualifications, content_category,
        vertical_profile, author_user_id, published_at, version,
        content_sha256, approved_at, approved_by_user_id,
        published_by_user_id, last_review_comment,
        created_at, updated_at
    """


def _serialize_row(row: dict[str, Any]) -> dict[str, Any]:
    d = dict(row)
    for key in ("id", "author_user_id", "approved_by_user_id", "published_by_user_id", "created_by_user_id", "actor_user_id"):
        val = d.get(key)
        if isinstance(val, uuid.UUID):
            d[key] = str(val)
    for key in ("created_at", "updated_at", "published_at", "approved_at"):
        val = d.get(key)
        if val is not None and hasattr(val, "isoformat"):
            d[key] = val.isoformat()
    return d


def tenant_content_list(
    tenant_id: int,
    *,
    status: str | None = None,
) -> list[dict[str, Any]]:
    params: list[Any] = [tenant_id]
    where = "tenant_id = %s"
    if status:
        where += " AND status = %s"
        params.append(status.strip().lower())
    cols = _content_select_columns()
    with pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                f"""
                SELECT {cols}
                FROM tenant_content
                WHERE {where}
                ORDER BY updated_at DESC, created_at DESC
                """,
                tuple(params),
            )
            rows = cur.fetchall()
        conn.commit()
    return [_serialize_row(dict(r)) for r in rows]


def tenant_content_get(content_id: uuid.UUID, tenant_id: int) -> dict[str, Any] | None:
    cols = _content_select_columns()
    with pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                f"""
                SELECT {cols}
                FROM tenant_content
                WHERE id = %s AND tenant_id = %s
                """,
                (content_id, tenant_id),
            )
            row = cur.fetchone()
        conn.commit()
    return _serialize_row(dict(row)) if row else None


def tenant_content_get_published_by_slug(tenant_id: int, slug: str) -> dict[str, Any] | None:
    slug_norm = (slug or "").strip().lower()
    if not slug_norm:
        return None
    cols = _content_select_columns()
    with pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                f"""
                SELECT {cols}
                FROM tenant_content
                WHERE tenant_id = %s AND slug = %s AND status = 'published'
                """,
                (tenant_id, slug_norm),
            )
            row = cur.fetchone()
        conn.commit()
    return _serialize_row(dict(row)) if row else None


def tenant_content_slug_exists(tenant_id: int, slug: str, *, exclude_id: uuid.UUID | None = None) -> bool:
    slug_norm = (slug or "").strip().lower()
    if not slug_norm:
        return False
    params: list[Any] = [tenant_id, slug_norm]
    extra = ""
    if exclude_id is not None:
        extra = " AND id <> %s"
        params.append(exclude_id)
    with pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT 1 FROM tenant_content WHERE tenant_id = %s AND slug = %s{extra} LIMIT 1",
                tuple(params),
            )
            ok = cur.fetchone() is not None
        conn.commit()
    return ok


def tenant_content_insert(
    *,
    tenant_id: int,
    slug: str,
    title: str,
    body_md: str,
    content_sha256: str,
    author_user_id: uuid.UUID,
    source_type: str = "self_authored",
    disclaimer_level: str = "learning_aid",
    vertical_profile: str | None = None,
    target_profession_roles: list[str] | None = None,
    target_departments: list[str] | None = None,
    required_qualifications: list[str] | None = None,
    content_category: str | None = None,
) -> dict[str, Any]:
    content_id = uuid.uuid4()
    now = datetime.now(UTC)
    cols = _content_select_columns()
    with pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                f"""
                INSERT INTO tenant_content (
                  id, tenant_id, slug, title, body_md, status, source_type,
                  disclaimer_level, target_profession_roles, target_departments,
                  required_qualifications, content_category,
                  vertical_profile, author_user_id, version, content_sha256,
                  created_at, updated_at
                )
                VALUES (%s, %s, %s, %s, %s, 'draft', %s, %s, %s, %s, %s, %s, %s, %s, 1, %s, %s, %s)
                RETURNING {cols}
                """,
                (
                    content_id,
                    tenant_id,
                    slug.strip().lower(),
                    title.strip(),
                    body_md,
                    source_type,
                    disclaimer_level,
                    Json(target_profession_roles or []),
                    Json(target_departments or []),
                    Json(required_qualifications or []),
                    (content_category or "").strip() or None,
                    (vertical_profile or "").strip() or None,
                    author_user_id,
                    content_sha256,
                    now,
                    now,
                ),
            )
            row = cur.fetchone()
        conn.commit()
    return _serialize_row(dict(row))


def tenant_content_update(
    content_id: uuid.UUID,
    tenant_id: int,
    *,
    slug: str | None = None,
    title: str | None = None,
    body_md: str | None = None,
    content_sha256: str | None = None,
    status: str | None = None,
    disclaimer_level: str | None = None,
    vertical_profile: str | None = None,
    target_profession_roles: list[str] | None = None,
    target_departments: list[str] | None = None,
    required_qualifications: list[str] | None = None,
    content_category: str | None = None,
    published_at: datetime | None = None,
    approved_at: datetime | None = None,
    approved_by_user_id: uuid.UUID | None = None,
    published_by_user_id: uuid.UUID | None = None,
    last_review_comment: str | None = None,
    version: int | None = None,
    clear_published_at: bool = False,
    clear_approved: bool = False,
) -> dict[str, Any] | None:
    sets: list[str] = ["updated_at = now()"]
    params: list[Any] = []
    if slug is not None:
        sets.append("slug = %s")
        params.append(slug.strip().lower())
    if title is not None:
        sets.append("title = %s")
        params.append(title.strip())
    if body_md is not None:
        sets.append("body_md = %s")
        params.append(body_md)
    if content_sha256 is not None:
        sets.append("content_sha256 = %s")
        params.append(content_sha256)
    if status is not None:
        sets.append("status = %s")
        params.append(status.strip().lower())
    if disclaimer_level is not None:
        sets.append("disclaimer_level = %s")
        params.append(disclaimer_level.strip().lower())
    if vertical_profile is not None:
        sets.append("vertical_profile = %s")
        params.append((vertical_profile or "").strip() or None)
    if target_profession_roles is not None:
        sets.append("target_profession_roles = %s")
        params.append(Json(target_profession_roles))
    if target_departments is not None:
        sets.append("target_departments = %s")
        params.append(Json(target_departments))
    if required_qualifications is not None:
        sets.append("required_qualifications = %s")
        params.append(Json(required_qualifications))
    if content_category is not None:
        sets.append("content_category = %s")
        params.append((content_category or "").strip() or None)
    if version is not None:
        sets.append("version = %s")
        params.append(int(version))
    if last_review_comment is not None:
        sets.append("last_review_comment = %s")
        params.append(last_review_comment.strip() or None)
    if clear_approved:
        sets.append("approved_at = NULL")
        sets.append("approved_by_user_id = NULL")
    elif approved_at is not None:
        sets.append("approved_at = %s")
        params.append(approved_at)
        if approved_by_user_id is not None:
            sets.append("approved_by_user_id = %s")
            params.append(approved_by_user_id)
    if published_by_user_id is not None:
        sets.append("published_by_user_id = %s")
        params.append(published_by_user_id)
    if clear_published_at:
        sets.append("published_at = NULL")
        sets.append("published_by_user_id = NULL")
    elif published_at is not None:
        sets.append("published_at = %s")
        params.append(published_at)
    params.extend([content_id, tenant_id])
    cols = _content_select_columns()
    with pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                f"""
                UPDATE tenant_content SET {', '.join(sets)}
                WHERE id = %s AND tenant_id = %s
                RETURNING {cols}
                """,
                tuple(params),
            )
            row = cur.fetchone()
        conn.commit()
    return _serialize_row(dict(row)) if row else None


def tenant_content_version_insert(
    *,
    content_id: uuid.UUID,
    tenant_id: int,
    version: int,
    title: str,
    body_md: str,
    content_sha256: str,
    created_by_user_id: uuid.UUID,
    snapshot_reason: str = "publish",
) -> dict[str, Any]:
    cols = """
        id, content_id, tenant_id, version, title, body_md, content_sha256,
        snapshot_reason, created_at, created_by_user_id
    """
    with pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                f"""
                INSERT INTO tenant_content_versions (
                  content_id, tenant_id, version, title, body_md, content_sha256,
                  snapshot_reason, created_by_user_id
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING {cols}
                """,
                (
                    content_id,
                    tenant_id,
                    int(version),
                    title.strip(),
                    body_md,
                    content_sha256,
                    snapshot_reason.strip().lower(),
                    created_by_user_id,
                ),
            )
            row = cur.fetchone()
        conn.commit()
    return _serialize_row(dict(row))


def tenant_content_versions_list(content_id: uuid.UUID, tenant_id: int) -> list[dict[str, Any]]:
    with pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT id, content_id, tenant_id, version, title, body_md, content_sha256,
                       snapshot_reason, created_at, created_by_user_id
                FROM tenant_content_versions
                WHERE content_id = %s AND tenant_id = %s
                ORDER BY version DESC
                """,
                (content_id, tenant_id),
            )
            rows = cur.fetchall()
        conn.commit()
    return [_serialize_row(dict(r)) for r in rows]


def tenant_content_version_get(
    content_id: uuid.UUID,
    tenant_id: int,
    version: int,
) -> dict[str, Any] | None:
    with pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT id, content_id, tenant_id, version, title, body_md, content_sha256,
                       snapshot_reason, created_at, created_by_user_id
                FROM tenant_content_versions
                WHERE content_id = %s AND tenant_id = %s AND version = %s
                """,
                (content_id, tenant_id, int(version)),
            )
            row = cur.fetchone()
        conn.commit()
    return _serialize_row(dict(row)) if row else None


def tenant_content_audit_insert(
    *,
    content_id: uuid.UUID,
    tenant_id: int,
    event_type: str,
    actor_user_id: uuid.UUID,
    comment: str | None = None,
    content_version: int | None = None,
) -> dict[str, Any]:
    with pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                INSERT INTO tenant_content_audit_events (
                  content_id, tenant_id, event_type, actor_user_id, comment, content_version
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id, content_id, tenant_id, event_type, actor_user_id,
                          comment, content_version, created_at
                """,
                (
                    content_id,
                    tenant_id,
                    event_type.strip().lower(),
                    actor_user_id,
                    (comment or "").strip() or None,
                    content_version,
                ),
            )
            row = cur.fetchone()
        conn.commit()
    return _serialize_row(dict(row))


def tenant_content_audit_list(content_id: uuid.UUID, tenant_id: int) -> list[dict[str, Any]]:
    with pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT id, content_id, tenant_id, event_type, actor_user_id,
                       comment, content_version, created_at
                FROM tenant_content_audit_events
                WHERE content_id = %s AND tenant_id = %s
                ORDER BY created_at DESC
                """,
                (content_id, tenant_id),
            )
            rows = cur.fetchall()
        conn.commit()
    return [_serialize_row(dict(r)) for r in rows]
