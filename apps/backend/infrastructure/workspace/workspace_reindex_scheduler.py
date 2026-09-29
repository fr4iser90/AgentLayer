"""Optional nightly / periodic full workspace reindex (operator flag)."""

from __future__ import annotations

import logging

from apps.backend.infrastructure.platform.poll_loop import PollLoop

logger = logging.getLogger(__name__)

# The pass itself decides which workspaces are stale, so this interval only
# bounds how long a stale index can sit before something notices.
_CHECK_INTERVAL_SEC = 3600


def start_workspace_reindex_scheduler() -> None:
    _worker.start()


def stop_workspace_reindex_scheduler() -> None:
    _worker.stop()


def _run_nightly_pass() -> None:
    from apps.backend.infrastructure.settings.operator_settings import fetch_operator_settings_row
    from apps.backend.infrastructure.workspace.workspace_columns import workspace_row_to_api
    from apps.backend.infrastructure.workspace.workspace_retrieval import start_semantic_index_async
    from apps.backend.infrastructure.workspace.workspace_retrieval_bootstrap import is_index_stale

    row = fetch_operator_settings_row()
    if not row.get("workspace_nightly_reindex_enabled"):
        return

    from apps.backend.infrastructure.db import db

    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, owner_user_id, name, path, source, git_url, git_branch, access_role,
                       created_at, updated_at, verify_command, verify_required, mcp_stdio_servers_json,
                       semantic_index_enabled, retrieval_enabled, last_index_at, last_index_stats, last_index_error,
                       docs_rag_enabled, last_docs_rag_at, last_docs_rag_stats, last_docs_rag_error,
                       index_on_write, graph_index_enabled, retrieve_context_sources
                FROM project_workspaces
                WHERE semantic_index_enabled IS NOT FALSE
                ORDER BY updated_at DESC
                LIMIT 100
                """
            )
            rows = cur.fetchall()

    started = 0
    for row in rows:
        api = workspace_row_to_api(row)
        if not is_index_stale(api):
            continue
        wid = str(api["id"])
        path = api.get("path")
        if not isinstance(path, str) or not path.strip():
            continue
        kick = start_semantic_index_async(wid, path, max_files=5000, mode="code")
        if kick.get("started"):
            started += 1
    if started:
        logger.info("nightly reindex: started %s workspace index job(s)", started)


_worker = PollLoop(
    name="workspace-reindex-scheduler",
    iteration=_run_nightly_pass,
    poll_sec=_CHECK_INTERVAL_SEC,
    join_sec=15.0,
    failure_log="workspace nightly reindex pass failed",
)
