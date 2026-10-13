"""``agent_tasks.status`` gains ``failed``.

The background runner already tried to write it: the terminal write at the end of
a task run says ``"failed" if failed else "done"``. ``failed`` was never part of
the vocabulary — not in the store's set, not in this CHECK — and both the store
and the CHECK treat an unknown status as something to drop rather than reject.
The UPDATE therefore ran, moved ``updated_at``, kept ``in_progress``, and handed
back the row: the runner believed it had reported a failure.

That is the whole bug class, and it is worse than a wrong label. The runner only
picks up ``status = 'queued'``, so a task that crashed stayed ``in_progress``
forever — not failed, not retryable, indistinguishable from a task still running.

``blocked`` was the alternative and is wrong: the runner already uses it for
"could not start" (no catalog LLM), a state a user unblocks by configuring a
model. A crashed run needs a retry, not a configuration change. One status for
both would make the queue's blocked count mean two opposite things.

The constraint is found by definition, not by name. schema_057 declared it inline
in the column list, so PostgreSQL named it — asserting the name here would break
on any database where the table arrived through a different path.

"""

from __future__ import annotations

from alembic import op

revision = "schema_139"
down_revision = "schema_138"
branch_labels = None
depends_on = None


_TABLE = "agent_tasks"
_CONSTRAINT = "agent_tasks_status_check"
_STATUSES = (
    "draft",
    "planning",
    "queued",
    "in_progress",
    "blocked",
    "failed",
    "done",
    "cancelled",
)
_STATUS_LIST = ", ".join(f"'{s}'" for s in _STATUSES)


def upgrade() -> None:
    op.execute(
        f"""
        DO $$
        DECLARE r record;
        BEGIN
            FOR r IN
                SELECT con.conname
                FROM pg_constraint con
                WHERE con.conrelid = '{_TABLE}'::regclass
                  AND con.contype = 'c'
                  AND pg_get_constraintdef(con.oid) LIKE '%status%'
                  AND pg_get_constraintdef(con.oid) LIKE '%draft%'
            LOOP
                EXECUTE format('ALTER TABLE {_TABLE} DROP CONSTRAINT %I', r.conname);
            END LOOP;
        END $$;
        """
    )
    op.execute(
        f"""
        ALTER TABLE {_TABLE}
            ADD CONSTRAINT {_CONSTRAINT}
            CHECK (status IN ({_STATUS_LIST}));
        """
    )


def downgrade() -> None:
    # A row that failed cannot be renamed back into the old vocabulary without
    # inventing a state, so the failures are moved to 'blocked' — the closest
    # non-terminal reading — before the narrower CHECK goes back in.
    op.execute(f"UPDATE {_TABLE} SET status = 'blocked' WHERE status = 'failed';")
    op.execute(f"ALTER TABLE {_TABLE} DROP CONSTRAINT IF EXISTS {_CONSTRAINT};")
    op.execute(
        f"""
        ALTER TABLE {_TABLE}
            ADD CONSTRAINT {_CONSTRAINT}
            CHECK (status IN ('draft', 'planning', 'queued', 'in_progress',
                              'blocked', 'done', 'cancelled'));
        """
    )