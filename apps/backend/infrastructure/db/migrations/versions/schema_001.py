"""Single baseline migration — applies ``sql/schema.sql`` (full current schema).

Revision ID: schema_001
Revises: (none)
Head: this revision only.

Use on empty databases: ``alembic upgrade head``. Older incremental revisions were removed;
existing deployments should dump data, recreate DB, restore data if needed, or keep a backup branch.
"""
from __future__ import annotations

import os
import re

from alembic import op

revision = "schema_001"
down_revision = None
branch_labels = None
depends_on = None


def _split_sql_statements(sql: str) -> list[str]:
    """Split schema snapshot into executable statements (respect statement-ending semicolons)."""
    lines: list[str] = []
    for line in sql.splitlines():
        if line.strip().startswith("--"):
            continue
        lines.append(line)
    blob = "\n".join(lines)
    parts = re.split(r";\s*\n", blob)
    out: list[str] = []
    for part in parts:
        stmt = part.strip()
        if stmt:
            out.append(stmt + ";")
    return out


def upgrade() -> None:
    sql_file = os.path.join(os.path.dirname(__file__), "..", "sql", "schema.sql")
    with open(sql_file, encoding="utf-8") as f:
        for stmt in _split_sql_statements(f.read()):
            op.execute(stmt)


def downgrade() -> None:
    pass
