from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from typing import Any

from psycopg.rows import dict_row
from psycopg.types.json import Json

from apps.backend.infrastructure.db.db import pool


def _serialize(row: dict[str, Any]) -> dict[str, Any]:
    d = dict(row)
    for key in ("id", "profession_role_id", "department_id", "user_id", "author_user_id"):
        if key in d and isinstance(d[key], uuid.UUID):
            d[key] = str(d[key])
    for key in ("created_at", "updated_at", "published_at"):
        val = d.get(key)
        if val is not None and hasattr(val, "isoformat"):
            d[key] = val.isoformat()
    vu = d.get("valid_until")
    if isinstance(vu, date):
        d["valid_until"] = vu.isoformat()
    return d


# --- Departments ---


def departments_list(tenant_id: int) -> list[dict[str, Any]]:
    with pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT id, tenant_id, slug, name, created_at
                FROM tenant_departments WHERE tenant_id = %s ORDER BY name ASC
                """,
                (tenant_id,),
            )
            rows = cur.fetchall()
        conn.commit()
    return [_serialize(dict(r)) for r in rows]


def department_insert(tenant_id: int, slug: str, name: str) -> dict[str, Any]:
    dept_id = uuid.uuid4()
    with pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                INSERT INTO tenant_departments (id, tenant_id, slug, name)
                VALUES (%s, %s, %s, %s)
                RETURNING id, tenant_id, slug, name, created_at
                """,
                (dept_id, tenant_id, slug.strip().lower(), name.strip()),
            )
            row = cur.fetchone()
        conn.commit()
    return _serialize(dict(row))


def department_get(dept_id: uuid.UUID, tenant_id: int) -> dict[str, Any] | None:
    with pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT id, tenant_id, slug, name, created_at FROM tenant_departments WHERE id = %s AND tenant_id = %s",
                (dept_id, tenant_id),
            )
            row = cur.fetchone()
        conn.commit()
    return _serialize(dict(row)) if row else None


def department_get_by_slug(tenant_id: int, slug: str) -> dict[str, Any] | None:
    with pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT id, tenant_id, slug, name, created_at FROM tenant_departments WHERE tenant_id = %s AND slug = %s",
                (tenant_id, slug.strip().lower()),
            )
            row = cur.fetchone()
        conn.commit()
    return _serialize(dict(row)) if row else None


# --- Profession roles ---


def profession_roles_list(tenant_id: int) -> list[dict[str, Any]]:
    with pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT id, tenant_id, slug, name, role_kind, content_categories, created_at
                FROM tenant_profession_roles WHERE tenant_id = %s ORDER BY name ASC
                """,
                (tenant_id,),
            )
            rows = cur.fetchall()
        conn.commit()
    return [_serialize(dict(r)) for r in rows]


def profession_role_insert(
    tenant_id: int,
    slug: str,
    name: str,
    role_kind: str,
    content_categories: list[str] | None = None,
) -> dict[str, Any]:
    role_id = uuid.uuid4()
    with pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                INSERT INTO tenant_profession_roles
                  (id, tenant_id, slug, name, role_kind, content_categories)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id, tenant_id, slug, name, role_kind, content_categories, created_at
                """,
                (
                    role_id,
                    tenant_id,
                    slug.strip().lower(),
                    name.strip(),
                    role_kind.strip().lower(),
                    Json(content_categories or []),
                ),
            )
            row = cur.fetchone()
        conn.commit()
    return _serialize(dict(row))


def profession_role_get(role_id: uuid.UUID, tenant_id: int) -> dict[str, Any] | None:
    with pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT id, tenant_id, slug, name, role_kind, content_categories, created_at
                FROM tenant_profession_roles WHERE id = %s AND tenant_id = %s
                """,
                (role_id, tenant_id),
            )
            row = cur.fetchone()
        conn.commit()
    return _serialize(dict(row)) if row else None


def profession_role_get_by_slug(tenant_id: int, slug: str) -> dict[str, Any] | None:
    with pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT id, tenant_id, slug, name, role_kind, content_categories, created_at
                FROM tenant_profession_roles WHERE tenant_id = %s AND slug = %s
                """,
                (tenant_id, slug.strip().lower()),
            )
            row = cur.fetchone()
        conn.commit()
    return _serialize(dict(row)) if row else None


def profession_roles_count(tenant_id: int) -> int:
    with pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM tenant_profession_roles WHERE tenant_id = %s", (tenant_id,))
            row = cur.fetchone()
        conn.commit()
    return int(row[0]) if row else 0


# --- Assignments ---


def profession_assignment_get(user_id: uuid.UUID, tenant_id: int) -> dict[str, Any] | None:
    with pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT a.user_id, a.tenant_id, a.profession_role_id, a.department_id,
                       a.created_at, a.updated_at,
                       r.slug AS profession_role_slug, r.name AS profession_role_name,
                       r.role_kind, r.content_categories,
                       d.slug AS department_slug, d.name AS department_name
                FROM user_profession_assignments a
                JOIN tenant_profession_roles r ON r.id = a.profession_role_id
                LEFT JOIN tenant_departments d ON d.id = a.department_id
                WHERE a.user_id = %s AND a.tenant_id = %s
                """,
                (user_id, tenant_id),
            )
            row = cur.fetchone()
        conn.commit()
    return _serialize(dict(row)) if row else None


def profession_assignment_upsert(
    user_id: uuid.UUID,
    tenant_id: int,
    profession_role_id: uuid.UUID,
    department_id: uuid.UUID | None,
) -> dict[str, Any]:
    now = datetime.now(UTC)
    with pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                INSERT INTO user_profession_assignments
                  (user_id, tenant_id, profession_role_id, department_id, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (user_id, tenant_id) DO UPDATE SET
                  profession_role_id = EXCLUDED.profession_role_id,
                  department_id = EXCLUDED.department_id,
                  updated_at = EXCLUDED.updated_at
                RETURNING user_id, tenant_id, profession_role_id, department_id, created_at, updated_at
                """,
                (user_id, tenant_id, profession_role_id, department_id, now, now),
            )
            row = cur.fetchone()
        conn.commit()
    base = _serialize(dict(row))
    enriched = profession_assignment_get(user_id, tenant_id)
    return enriched or base


def profession_assignments_list(tenant_id: int) -> list[dict[str, Any]]:
    with pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT a.user_id, a.tenant_id, a.profession_role_id, a.department_id,
                       a.created_at, a.updated_at,
                       r.slug AS profession_role_slug, r.name AS profession_role_name,
                       r.role_kind, r.content_categories,
                       d.slug AS department_slug, d.name AS department_name,
                       u.email AS user_email
                FROM user_profession_assignments a
                JOIN tenant_profession_roles r ON r.id = a.profession_role_id
                LEFT JOIN tenant_departments d ON d.id = a.department_id
                JOIN users u ON u.id = a.user_id
                WHERE a.tenant_id = %s
                ORDER BY u.email ASC
                """,
                (tenant_id,),
            )
            rows = cur.fetchall()
        conn.commit()
    return [_serialize(dict(r)) for r in rows]


# --- Qualifications ---


def qualifications_list(user_id: uuid.UUID, tenant_id: int) -> list[dict[str, Any]]:
    with pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT id, user_id, tenant_id, qualification_type, valid_until, evidence_ref, created_at
                FROM user_qualifications
                WHERE user_id = %s AND tenant_id = %s
                ORDER BY qualification_type ASC
                """,
                (user_id, tenant_id),
            )
            rows = cur.fetchall()
        conn.commit()
    return [_serialize(dict(r)) for r in rows]


def qualification_insert(
    user_id: uuid.UUID,
    tenant_id: int,
    qualification_type: str,
    valid_until: date | None,
    evidence_ref: str | None,
) -> dict[str, Any]:
    qid = uuid.uuid4()
    with pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                INSERT INTO user_qualifications
                  (id, user_id, tenant_id, qualification_type, valid_until, evidence_ref)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id, user_id, tenant_id, qualification_type, valid_until, evidence_ref, created_at
                """,
                (
                    qid,
                    user_id,
                    tenant_id,
                    qualification_type.strip().lower(),
                    valid_until,
                    (evidence_ref or "").strip() or None,
                ),
            )
            row = cur.fetchone()
        conn.commit()
    return _serialize(dict(row))


def qualification_delete(qualification_id: uuid.UUID, tenant_id: int) -> bool:
    with pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM user_qualifications WHERE id = %s AND tenant_id = %s",
                (qualification_id, tenant_id),
            )
            n = cur.rowcount or 0
        conn.commit()
    return n > 0


def tenant_content_get_by_source_uri(tenant_id: int, source_uri: str) -> dict[str, Any] | None:
    """Resolve CMS row from RAG source_uri ``tenant-content/{uuid}``."""
    uri = (source_uri or "").strip()
    prefix = "tenant-content/"
    if not uri.startswith(prefix):
        return None
    raw_id = uri[len(prefix) :].strip()
    try:
        cid = uuid.UUID(raw_id)
    except ValueError:
        return None
    with pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT id, tenant_id, slug, title, status, target_profession_roles,
                       target_departments, required_qualifications, content_category
                FROM tenant_content WHERE id = %s AND tenant_id = %s
                """,
                (cid, tenant_id),
            )
            row = cur.fetchone()
        conn.commit()
    if not row:
        return None
    d = dict(row)
    if isinstance(d.get("id"), uuid.UUID):
        d["id"] = str(d["id"])
    return d
