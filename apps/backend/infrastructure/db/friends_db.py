"""
Friendship System Database Functions
"""

from __future__ import annotations

import uuid
from typing import Any
from psycopg.rows import dict_row

from apps.backend.infrastructure.db.db import pool


def friend_request_create(tenant_id: int, from_user_id: uuid.UUID, to_user_id: uuid.UUID, message: str | None = None) -> bool:
    """Create a new friend request between two users"""
    with pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO friend_requests (tenant_id, from_user_id, to_user_id, message, status)
                VALUES (%s, %s, %s, %s, 'pending')
                ON CONFLICT (from_user_id, to_user_id) DO NOTHING
                """,
                (tenant_id, from_user_id, to_user_id, message),
            )
            ok = cur.rowcount > 0
        conn.commit()
    return ok


def friend_request_get(request_id: int) -> dict[str, Any] | None:
    """Get a single friend request by id"""
    with pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT id, tenant_id, from_user_id, to_user_id, status, message, created_at, responded_at
                FROM friend_requests
                WHERE id = %s
                """,
                (request_id,),
            )
            row = cur.fetchone()
        conn.commit()
    return dict(row) if row else None


def friend_request_get_between(user_id_1: uuid.UUID, user_id_2: uuid.UUID) -> dict[str, Any] | None:
    """Get pending friend request between two users (any direction)"""
    with pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT id, tenant_id, from_user_id, to_user_id, status, message, created_at, responded_at
                FROM friend_requests
                WHERE (from_user_id = %s AND to_user_id = %s) OR (from_user_id = %s AND to_user_id = %s)
                AND status = 'pending'
                LIMIT 1
                """,
                (user_id_1, user_id_2, user_id_2, user_id_1),
            )
            row = cur.fetchone()
        conn.commit()
    return dict(row) if row else None


def friend_requests_incoming(user_id: uuid.UUID) -> list[dict[str, Any]]:
    """Get all incoming pending friend requests for a user"""
    with pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT fr.id, fr.from_user_id, fr.message, fr.created_at, u.email, u.display_name
                FROM friend_requests fr
                JOIN users u ON fr.from_user_id = u.id
                WHERE fr.to_user_id = %s AND fr.status = 'pending'
                ORDER BY fr.created_at DESC
                """,
                (user_id,),
            )
            rows = cur.fetchall()
        conn.commit()
    return [dict(r) for r in rows]


def friend_requests_outgoing(user_id: uuid.UUID) -> list[dict[str, Any]]:
    """Get all outgoing pending friend requests for a user"""
    with pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT fr.id, fr.to_user_id, fr.message, fr.created_at, u.email, u.display_name
                FROM friend_requests fr
                JOIN users u ON fr.to_user_id = u.id
                WHERE fr.from_user_id = %s AND fr.status = 'pending'
                ORDER BY fr.created_at DESC
                """,
                (user_id,),
            )
            rows = cur.fetchall()
        conn.commit()
    return [dict(r) for r in rows]


def friend_request_accept(request_id: int, tenant_id: int, from_user_id: uuid.UUID, to_user_id: uuid.UUID) -> bool:
    """Accept a friend request and create mutual friend entries"""
    with pool().connection() as conn:
        with conn.cursor() as cur:
            # Update request status
            cur.execute(
                """
                UPDATE friend_requests
                SET status = 'accepted', responded_at = NOW()
                WHERE id = %s AND status = 'pending'
                """,
                (request_id,),
            )
            if cur.rowcount < 1:
                conn.rollback()
                return False

            # Create mutual friend entries
            cur.execute(
                """
                INSERT INTO friends (tenant_id, user_id, friend_user_id, created_at)
                VALUES (%s, %s, %s, NOW()), (%s, %s, %s, NOW())
                ON CONFLICT (user_id, friend_user_id) DO NOTHING
                """,
                (tenant_id, from_user_id, to_user_id, tenant_id, to_user_id, from_user_id),
            )

            # Automatically add each other to known_people
            cur.execute(
                """
                UPDATE user_agent_profile
                SET known_people = COALESCE(known_people, '[]'::jsonb) || jsonb_build_object(
                    'name', COALESCE(u2.display_name, u2.email),
                    'email', u2.email
                )
                FROM users u2
                WHERE user_agent_profile.user_id = %s AND u2.id = %s
                """,
                (from_user_id, to_user_id),
            )

            cur.execute(
                """
                UPDATE user_agent_profile
                SET known_people = COALESCE(known_people, '[]'::jsonb) || jsonb_build_object(
                    'name', COALESCE(u1.display_name, u1.email),
                    'email', u1.email
                )
                FROM users u1
                WHERE user_agent_profile.user_id = %s AND u1.id = %s
                """,
                (to_user_id, from_user_id),
            )

        conn.commit()
    return True


def friend_request_decline(request_id: int) -> bool:
    """Decline a friend request"""
    with pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE friend_requests
                SET status = 'declined', responded_at = NOW()
                WHERE id = %s AND status = 'pending'
                """,
                (request_id,),
            )
            ok = cur.rowcount > 0
        conn.commit()
    return ok


def friend_get(user_id: uuid.UUID, friend_user_id: uuid.UUID) -> dict[str, Any] | None:
    """Check if two users are friends"""
    with pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT id, tenant_id, user_id, friend_user_id, relation, note, created_at
                FROM friends
                WHERE user_id = %s AND friend_user_id = %s
                """,
                (user_id, friend_user_id),
            )
            row = cur.fetchone()
        conn.commit()
    return dict(row) if row else None


def friends_list(user_id: uuid.UUID) -> list[dict[str, Any]]:
    """List all confirmed friends for a user"""
    with pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT f.id, f.friend_user_id, f.relation, f.note, f.created_at, u.email, u.display_name, u.discord_user_id
                FROM friends f
                JOIN users u ON f.friend_user_id = u.id
                WHERE f.user_id = %s
                ORDER BY f.created_at DESC
                """,
                (user_id,),
            )
            rows = cur.fetchall()
        conn.commit()
    return [dict(r) for r in rows]


def friend_remove(user_id: uuid.UUID, friend_user_id: uuid.UUID) -> bool:
    """Remove a friend (removes both sides)"""
    with pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM friends
                WHERE (user_id = %s AND friend_user_id = %s) OR (user_id = %s AND friend_user_id = %s)
                """,
                (user_id, friend_user_id, friend_user_id, user_id),
            )
            ok = cur.rowcount > 0
        conn.commit()
    return ok


def friend_update(user_id: uuid.UUID, friend_user_id: uuid.UUID, relation: str | None = None, note: str | None = None) -> bool:
    """Update friend metadata fields for your side of the friendship"""
    with pool().connection() as conn:
        with conn.cursor() as cur:
            update_fields = []
            params = []
            
            if relation is not None:
                update_fields.append("relation = %s")
                params.append(relation)
            
            if note is not None:
                update_fields.append("note = %s")
                params.append(note)
            
            if not update_fields:
                return True

            params.append(user_id)
            params.append(friend_user_id)

            # SECURITY: Column names in `update_fields` come from function parameters
            # (relation, note). All values are parameterized via %s placeholders.
            cur.execute(
                f"""
                UPDATE friends
                SET {', '.join(update_fields)}
                WHERE user_id = %s AND friend_user_id = %s
                """,
                tuple(params)
            )
            
            ok = cur.rowcount > 0
        conn.commit()
    return ok
