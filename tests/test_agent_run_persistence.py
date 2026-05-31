"""Agent run persistence: resilient FK handling and task validation."""

from __future__ import annotations

import json
import uuid
from unittest.mock import MagicMock, patch

import psycopg

from apps.backend.infrastructure import agent_runs_store


def test_insert_run_start_resilient_strips_missing_task() -> None:
    run_id = uuid.uuid4()
    user_id = uuid.uuid4()
    task_id = uuid.uuid4()
    inserted: list[uuid.UUID | None] = []

    def fake_insert(**kwargs: object) -> dict:
        inserted.append(kwargs.get("task_id"))  # type: ignore[arg-type]
        return {"id": run_id}

    with patch(
        "apps.backend.infrastructure.agent_tasks_store.get_task",
        return_value=None,
    ):
        with patch.object(agent_runs_store, "insert_run_start", side_effect=fake_insert):
            with patch.object(agent_runs_store, "run_exists", return_value=False):
                row, warnings = agent_runs_store.insert_run_start_resilient(
                    run_id=run_id,
                    tenant_id=1,
                    user_id=user_id,
                    agent_id="coding",
                    task_id=task_id,
                )
    assert row.get("id") == run_id
    assert inserted == [None]
    assert any("active_task_id" in w for w in warnings)


def test_insert_run_start_resilient_retries_after_fk_error() -> None:
    run_id = uuid.uuid4()
    user_id = uuid.uuid4()
    calls: list[tuple[uuid.UUID | None, uuid.UUID | None]] = []

    def fake_insert(**kwargs: object) -> dict:
        t_id = kwargs.get("task_id")  # type: ignore[assignment]
        p_id = kwargs.get("parent_run_id")  # type: ignore[assignment]
        calls.append((t_id, p_id))
        if t_id is not None:
            raise psycopg.Error("fk")
        return {"id": run_id}

    task_id = uuid.uuid4()
    with patch(
        "apps.backend.infrastructure.agent_tasks_store.get_task",
        return_value={"tenant_id": 1},
    ):
        with patch.object(agent_runs_store, "insert_run_start", side_effect=fake_insert):
            with patch.object(agent_runs_store, "run_exists", return_value=True):
                row, warnings = agent_runs_store.insert_run_start_resilient(
                    run_id=run_id,
                    tenant_id=1,
                    user_id=user_id,
                    agent_id="coding",
                    task_id=task_id,
                )
    assert row.get("id") == run_id
    assert calls[-1] == (None, None)
    assert warnings


def test_resolve_valid_active_task_id_rejects_missing() -> None:
    from apps.backend.domain.agent_run_persistence import resolve_valid_active_task_id

    uid = uuid.uuid4()
    tid = uuid.uuid4()
    with patch(
        "apps.backend.infrastructure.agent_tasks_store.get_task",
        return_value=None,
    ):
        active, tu = resolve_valid_active_task_id(
            tenant_id=1, user_id=uid, candidate=str(tid)
        )
    assert active is None
    assert tu is None


def test_resolve_valid_active_task_id_accepts_accessible() -> None:
    from apps.backend.domain.agent_run_persistence import resolve_valid_active_task_id

    uid = uuid.uuid4()
    tid = uuid.uuid4()
    row = {"tenant_id": 1, "created_by_user_id": uid, "workspace_id": None}
    with patch(
        "apps.backend.infrastructure.agent_tasks_store.get_task",
        return_value=row,
    ):
        with patch(
            "apps.backend.domain.agent_run_persistence.user_may_access_task_row",
            return_value=True,
        ):
            active, tu = resolve_valid_active_task_id(
                tenant_id=1, user_id=uid, candidate=str(tid)
            )
    assert active == str(tid)
    assert tu == tid


def test_embedded_subagent_default_no_wall_clock_timeout() -> None:
    from apps.backend.core import config
    from plugins.tools.capabilities.platform._embedded_subagent import (
        run_embedded_subagent_sync,
    )

    uid = uuid.uuid4()
    ctx = {
        "parent_effective_model": "m1",
        "parent_model_catalog_owned_by": "provider_1",
        "user": type("U", (), {"id": uid})(),
    }
    with patch.object(config, "SUBAGENT_TIMEOUT_SEC", None):
        with patch("apps.backend.domain.identity.get_identity", return_value=(1, uid)):
            with patch(
                "plugins.tools.capabilities.platform._embedded_subagent.ThreadPoolExecutor"
            ) as tpe:
                pool = MagicMock()
                tpe.return_value.__enter__.return_value = pool
                fut = MagicMock()
                pool.submit.return_value = fut
                fut.result.return_value = {
                    "choices": [{"message": {"content": "done"}, "finish_reason": "stop"}]
                }
                with patch(
                    "apps.backend.infrastructure.agent_artifacts_store.create_artifact",
                    return_value={"id": uuid.uuid4()},
                ):
                    run_embedded_subagent_sync(
                        subagent_agent_id="coding",
                        prompt="work",
                        context=ctx,
                        tool_name="agent_delegate",
                        description="test",
                    )
                fut.result.assert_called_once_with()


def test_embedded_subagent_surfaces_api_error() -> None:
    from plugins.tools.capabilities.platform._embedded_subagent import (
        run_embedded_subagent_sync,
    )

    uid = uuid.uuid4()
    ctx = {
        "parent_effective_model": "m1",
        "parent_model_catalog_owned_by": "provider_1",
        "user": type("U", (), {"id": uid})(),
    }
    with patch("apps.backend.domain.identity.get_identity", return_value=(1, uid)):
        with patch(
            "plugins.tools.capabilities.platform._embedded_subagent.ThreadPoolExecutor"
        ) as tpe:
            pool = MagicMock()
            tpe.return_value.__enter__.return_value = pool
            pool.submit.return_value.result.return_value = {"error": "model unavailable"}
            out = run_embedded_subagent_sync(
                subagent_agent_id="coding",
                prompt="work",
                context=ctx,
                tool_name="agent_delegate",
                description="test",
            )
    data = json.loads(out)
    assert data.get("ok") is False
    assert "model unavailable" in (data.get("error") or "")
    assert data.get("problems")


def test_coding_task_register_only_marks_not_executed() -> None:
    from plugins.tools.capabilities.coding.coding_task import coding_task

    out = coding_task(
        {"description": "Check branch", "prompt": "Review security branch"},
        context=None,
    )
    data = json.loads(out)
    assert data.get("ok") is True
    assert data.get("mode") == "register_only"
    assert data.get("executed") is False
    assert data.get("warning")
