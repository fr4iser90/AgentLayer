"""P7a: agent submission staging + review queue.

Staging path for user-submitted agent drafts that a site admin reviews before
they are promoted into ``plugins/agents/<id>/``. Solves the long-standing gap
that agent definitions are pure files with no DB-backed review path.

- ``agent_submissions`` holds the proposed definition (``agent_yaml`` JSONB),
  the optional ``system_prompt`` text, a risk heuristic and the review
  lifecycle (``pending`` -> ``approved`` / ``rejected``).
- A partial unique on ``(agent_id) WHERE status = 'pending'`` prevents two
  live drafts colliding for the same slug; reviews may be retried afterwards.
"""

from __future__ import annotations

from alembic import op

revision = "schema_131"
down_revision = "schema_130"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE agent_submissions (
          id               UUID PRIMARY KEY,
          agent_id         TEXT NOT NULL,
          title            TEXT,
          description      TEXT,
          system_prompt    TEXT,
          agent_yaml       JSONB NOT NULL DEFAULT '[]'::jsonb,
          target_dir       TEXT,
          risk_level       TEXT NOT NULL DEFAULT 'low'
                           CHECK (risk_level IN ('low', 'medium', 'high')),
          status           TEXT NOT NULL DEFAULT 'pending'
                           CHECK (status IN ('pending', 'approved', 'rejected')),
          author_id        TEXT NOT NULL,
          reviewed_by      TEXT,
          reviewed_at      TIMESTAMPTZ,
          review_notes     TEXT,
          materialize_error TEXT,
          created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
          updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_agent_submissions_pending_agent_id "
        "ON agent_submissions (agent_id) WHERE status = 'pending'"
    )
    op.execute(
        "CREATE INDEX ix_agent_submissions_status ON agent_submissions (status)"
    )
    op.execute(
        "CREATE INDEX ix_agent_submissions_author ON agent_submissions (author_id)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS agent_submissions")
