"""Narrowed, owner-published views that a friend's read is served from.

ADR 0014 step 6: the projection contract behind the adapter registry.

Why a projection at all
----------------------
Before this, a shared read went to the live source on every call. For a
calendar that meant resolving the owner's ICS bearer URL inside the read.
Principle 1 kept the URL out of the result, but the read still *depended*
on the credential, and the shape of what crossed was whatever the live
source happened to return.

A projection inverts that. The owner runs a narrowing pass over their own
data and stores the result. The grantee's read touches only this row. A
field that was never written into the projection cannot leak from it, which
is a stronger guarantee than "we remembered to strip it" — and it holds
with no live source and no credential in the read path at all.

One row per (owner, type, identifier), not per grantee
----------------------------------------------------
The projection is **owner-owned**. It answers *what shape exists*, not
*who may read it*. The grant answers the second question, and it is
checked on every read, so revoking a grant stops serving immediately
without touching this row.

Keying per grantee instead would multiply one owner's data by their
friend count for no benefit: the narrowing is the owner's decision and is
the same for everyone they granted. It would also mean a revoke has to
find and delete rows, turning a cheap grant check into a delete that can
be missed.

The owner chooses the shape, once, for everyone
--------------------------------------------
``projection_kind`` records which narrowing the owner published — for a
calendar, ``availability`` (busy/free windows only) or ``events`` (titles
included). There is exactly one live projection per resource, so every
grantee of that resource sees the same shape. That is deliberate: a
per-grantee shape would put the owner's disclosure decision back into a
place they no longer control, and would make "what does Anna see of my
calendar" a question with many answers.

``expires_at`` is NOT NULL
------------------------
Every projection expires. A projection that never expires is a copy of
someone's data with no reason to be refreshed, and staleness is the one
cost this design accepts — so it is the one thing that must be bounded
explicitly rather than assumed. The reader treats a past ``expires_at`` as
"republish before serving", never as "serve anyway".

No FK on owner_user_id
---------------------
``share_permissions`` deliberately carries no referential constraints
(schema_039), and this table is read the same way: by the owner's id,
supplied by the grant check rather than by a join. A row whose owner is
gone is inert for the same reason a grant whose owner is gone is inert —
nothing resolves it. Matching the sibling table here also keeps the two
tables' lifetimes identical rather than making one cascade and the other
not.
"""

from __future__ import annotations

from alembic import op

revision = "schema_138"
down_revision = "schema_137"
branch_labels = None
depends_on = None


_TABLE = "share_projections"


def upgrade() -> None:
    op.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {_TABLE} (
            owner_user_id UUID NOT NULL,
            resource_type TEXT NOT NULL,
            resource_identifier TEXT NOT NULL,
            projection_kind TEXT NOT NULL,
            payload JSONB NOT NULL,
            generated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            expires_at TIMESTAMPTZ NOT NULL,
            PRIMARY KEY (owner_user_id, resource_type, resource_identifier)
        );
        """
    )

    # The sweeper asks "what has expired" and nothing else, so the index is
    # the whole query. A projection is small and the table is small; no
    # covering index is worth it.
    op.execute(
        f"""
        CREATE INDEX IF NOT EXISTS idx_{_TABLE}_expires_at
            ON {_TABLE} (expires_at);
        """
    )

    op.execute(
        f"""
        COMMENT ON TABLE {_TABLE} IS
            'Owner-published narrowed views behind the share adapter registry '
            '(ADR 0014 step 6). Keyed on the OWNER, never the grantee: the '
            'grant decides who may read, this row decides what exists to be '
            'read. payload must satisfy find_credential_keys() before it is '
            'stored — a credential must never reach this table. expires_at is '
            'NOT NULL: a projection that never expires is an unbounded copy '
            'of someone''s data.'
        """
    )
    op.execute(
        f"""
        COMMENT ON COLUMN {_TABLE}.projection_kind IS
            'Which narrowing the owner published. One live shape per resource, '
            'seen identically by every grantee of it.'
        """
    )
    op.execute(
        f"""
        COMMENT ON COLUMN {_TABLE}.expires_at IS
            'Freshness bound set by the adapter that published it. Past this '
            'moment the row must be republished before it is served, not '
            'served as-is.'
        """
    )


def downgrade() -> None:
    op.execute(f"DROP INDEX IF EXISTS idx_{_TABLE}_expires_at;")
    op.execute(f"DROP TABLE IF EXISTS {_TABLE};")
