"""Workspace delete must remove workspace-scoped agent_tasks first (FK check)."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

from apps.backend.infrastructure.workspace_service import (
    _delete_workspace_db_dependencies,
    delete_owned_workspace,
)


def test_delete_workspace_db_dependencies_deletes_agent_tasks() -> None:
    cur = MagicMock()
    wid = str(uuid.uuid4())
    _delete_workspace_db_dependencies(cur, wid)
    cur.execute.assert_called_once()
    assert "agent_tasks" in cur.execute.call_args[0][0]
    assert cur.execute.call_args[0][1] == (wid,)


def test_delete_owned_workspace_calls_task_cleanup_before_row_delete() -> None:
    uid = uuid.uuid4()
    wid = uuid.uuid4()
    calls: list[str] = []

    def fake_execute(sql: str, params: tuple = ()) -> None:
        calls.append(sql.strip().split()[0:3].__str__())

    cur = MagicMock()

    def _track(sql: str, params: tuple = ()) -> None:
        if "DELETE FROM agent_tasks" in sql:
            calls.append("agent_tasks")
        elif "DELETE FROM project_workspaces" in sql:
            calls.append("project_workspaces")

    cur.execute.side_effect = _track
    cur.fetchone.return_value = ("/tmp/ws", "e2e-test")

    conn = MagicMock()
    conn.cursor.return_value.__enter__ = lambda s: cur
    conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

    with patch("apps.backend.infrastructure.db.db.pool") as pool:
        pool.return_value.connection.return_value.__enter__ = lambda s: conn
        pool.return_value.connection.return_value.__exit__ = MagicMock(return_value=False)
        with patch(
            "apps.backend.infrastructure.workspace_service._delete_workspace_files"
        ):
            with patch(
                "apps.backend.infrastructure.workspace_service._delete_workspace_index_sidecars"
            ):
                ok = delete_owned_workspace(
                    workspace_id=str(wid), owner_user_id=uid
                )

    assert ok is True
    assert "agent_tasks" in calls
    assert calls.index("agent_tasks") < calls.index("project_workspaces")
