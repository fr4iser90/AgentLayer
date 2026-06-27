"""On-demand dashboard DB schema from ``dashboard.kind.json`` (``schema_sql``). Not run at server start."""

from __future__ import annotations

import logging

from apps.backend.infrastructure.db import db
from apps.backend.infrastructure.dashboards.dashboard_bundle import schema_sql_paths_for_kinds

logger = logging.getLogger(__name__)


def dashboard_tables_exist() -> bool:
    """True if ``user_dashboards`` exists (no error if table missing)."""
    try:
        with db.pool().connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT EXISTS (
                      SELECT 1 FROM information_schema.tables
                      WHERE table_schema = 'public' AND table_name = 'user_dashboards'
                    )
                    """
                )
                row = cur.fetchone()
            conn.commit()
        return bool(row and row[0])
    except Exception:
        logger.exception("dashboard_tables_exist check failed")
        return False


def ensure_dashboard_schema(kinds: list[str]) -> None:
    """Execute ``schema_sql`` only for the selected kinds (idempotent SQL). POST /install only."""
    if not kinds:
        raise ValueError("no kinds selected for dashboard schema install")
    paths = schema_sql_paths_for_kinds(kinds)
    if not paths:
        want = sorted({k.strip().lower() for k in kinds if k and str(k).strip()})
        msg = f"no schema_sql on disk for kinds: {want}"
        logger.error(msg)
        raise FileNotFoundError(msg)
    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            for sql_path in paths:
                sql = sql_path.read_text(encoding="utf-8")
                cur.execute(sql)
        conn.commit()
    logger.info("dashboard schema applied (%s file(s))", len(paths))
