"""Shared ``project_workspaces`` SELECT list and API row mapping."""

from __future__ import annotations

from datetime import datetime
from typing import Any

WORKSPACE_SELECT_SQL = """
    id, owner_user_id, name, path, source, git_url, git_branch, access_role,
    created_at, updated_at, verify_command, verify_required, mcp_stdio_servers_json,
    semantic_index_enabled, retrieval_enabled, last_index_at, last_index_stats, last_index_error
"""


def workspace_row_to_api(row: tuple) -> dict[str, Any]:
    mcp_raw = row[12]
    mcp_list: list[Any] | None = None
    if isinstance(mcp_raw, list) and len(mcp_raw) > 0:
        mcp_list = list(mcp_raw)
    last_stats = row[16]
    return {
        "id": str(row[0]),
        "owner_user_id": str(row[1]),
        "name": row[2],
        "path": row[3],
        "source": row[4],
        "git_url": row[5],
        "git_branch": row[6],
        "access_role": row[7],
        "created_at": row[8].isoformat() if row[8] else None,
        "updated_at": row[9].isoformat() if row[9] else None,
        "verify_command": row[10],
        "verify_required": bool(row[11]) if row[11] is not None else False,
        "mcp_stdio_servers": mcp_list,
        "semantic_index_enabled": bool(row[13]) if row[13] is not None else True,
        "retrieval_enabled": bool(row[14]) if row[14] is not None else True,
        "last_index_at": row[15].isoformat() if isinstance(row[15], datetime) else None,
        "last_index_stats": last_stats if isinstance(last_stats, dict) else None,
        "last_index_error": row[17],
    }
