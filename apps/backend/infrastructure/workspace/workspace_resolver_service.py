"""Infrastructure adapter for resolving project workspaces."""

from __future__ import annotations

import logging
from typing import Any

from apps.backend.domain.workspace import resolver as domain
from apps.backend.infrastructure.db import db
from apps.backend.infrastructure.workspace.workspace_columns import WORKSPACE_SELECT_SQL, workspace_row_to_api

logger = logging.getLogger(__name__)


class _WorkspaceResolverDeps:
    @staticmethod
    def resolve_db_workspace(workspace_id: str, user: Any) -> dict[str, Any] | None:
        try:
            with db.pool().connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        f"""
                        SELECT {WORKSPACE_SELECT_SQL}
                        FROM project_workspaces
                        WHERE id = %s AND (owner_user_id = %s OR access_role IN ('editor', 'viewer'))
                        """,
                        (str(workspace_id), user.id),
                    )
                    row = cur.fetchone()
            if not row:
                logger.debug("workspace not found or not accessible: %s", workspace_id)
                return None
            api = workspace_row_to_api(row)
            return {
                "type": "db",
                "state": domain.WorkspaceState.READY,
                "source": api["source"],
                "git_url": api.get("git_url"),
                "git_branch": api.get("git_branch"),
                "path": api["path"],
                "repo_path": api["path"],
                "name": api["name"],
                "id": api["id"],
                "owner_user_id": api["owner_user_id"],
                "access_role": api["access_role"],
                "verify_command": api.get("verify_command"),
                "verify_required": bool(api.get("verify_required", False)),
                "mcp_stdio_servers": api.get("mcp_stdio_servers"),
                "semantic_index_enabled": api.get("semantic_index_enabled", True),
                "retrieval_enabled": api.get("retrieval_enabled", True),
                "last_index_at": api.get("last_index_at"),
                "last_index_stats": api.get("last_index_stats"),
                "last_index_error": api.get("last_index_error"),
                "docs_rag_enabled": api.get("docs_rag_enabled", True),
                "last_docs_rag_at": api.get("last_docs_rag_at"),
                "last_docs_rag_stats": api.get("last_docs_rag_stats"),
                "last_docs_rag_error": api.get("last_docs_rag_error"),
                "index_on_write": api.get("index_on_write"),
                "graph_index_enabled": api.get("graph_index_enabled", True),
                "retrieve_context_sources": api.get("retrieve_context_sources"),
            }
        except Exception as exc:
            logger.error("failed to resolve workspace from DB: %s", exc)
            return None


domain.register_workspace_resolver_dependencies(_WorkspaceResolverDeps())

WorkspaceState = domain.WorkspaceState
is_workspace_ready = domain.is_workspace_ready
resolve_db_workspace = domain.resolve_db_workspace
resolve_source = domain.resolve_source
resolve_workspace = domain.resolve_workspace
