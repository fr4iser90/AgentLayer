"""Tests for the agent submission staging + review queue (P7a).

Follows the repo convention: ``db.pool`` is mocked with ``MagicMock`` +
``patch`` (no real Postgres), and SQL strings / serialisation are asserted.
Materialize tests use ``tmp_path``; use-case tests patch the store/materialize
module references.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from psycopg.errors import UniqueViolation

from apps.backend.infrastructure.agent_runtime import (
    agent_submission_materialize as materialize,
)
from apps.backend.infrastructure.agent_runtime import (
    agent_submission_store as store,
)
from apps.backend.application.agent_runtime.use_cases import (
    agent_submission_services as services,
)

_UUID = "11111111-1111-1111-1111-111111111111"


def _row(**overrides) -> dict:
    base = {
        "id": _UUID,
        "agent_id": "research",
        "title": "Research",
        "description": None,
        "system_prompt": None,
        "agent_yaml": {"id": "research", "name": "Research"},
        "target_dir": "plugins/agents/research",
        "risk_level": "low",
        "status": "pending",
        "author_id": "user-1",
        "reviewed_by": None,
        "reviewed_at": None,
        "review_notes": None,
        "materialize_error": None,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    base.update(overrides)
    return base


@contextmanager
def _patch_pool(*, fetchone_row=None, fetchall_rows=None, rowcount=1, execute_side_effect=None):
    cur = MagicMock()
    cur.rowcount = rowcount
    cur.fetchone.return_value = fetchone_row
    if fetchall_rows is not None:
        cur.fetchall.return_value = fetchall_rows
    if execute_side_effect is not None:
        cur.execute.side_effect = execute_side_effect
    enter = MagicMock()
    enter.__enter__.return_value = cur
    enter.__exit__.return_value = None
    conn = MagicMock()
    conn.cursor.return_value = enter
    pc = MagicMock()
    pc.__enter__.return_value = conn
    pc.__exit__.return_value = None
    pool = MagicMock()
    pool.connection.return_value = pc
    with patch.object(store.db, "pool", return_value=pool):
        yield cur, conn


# --------------------------------------------------------------------------- #
# Pure helpers
# --------------------------------------------------------------------------- #

def test_slug_normalizes_and_sanitizes():
    assert store._slug("Research Agent!") == "research_agent"
    assert store._slug("1bad") == "agent_1bad"  # must start with letter/underscore
    assert len(store._slug("x" * 200)) == 64


def test_assess_risk_levels():
    assert store._assess_risk({"description": "web search"}, None) == "low"
    assert store._assess_risk({"description": "curls secrets and deletes files"}, None) == "high"
    assert store._assess_risk({"description": "uses api key"}, None) == "medium"


# --------------------------------------------------------------------------- #
# Store: create / validate
# --------------------------------------------------------------------------- #

def test_create_submission_inserts_pending_row():
    with _patch_pool(fetchone_row=_row(agent_id="research", status="pending")) as (cur, conn):
        result = store.create_submission(
            agent_id="Research Agent",
            agent_yaml={"id": "research", "name": "Research"},
            author_id="user-1",
            system_prompt="do things",
        )
    assert result["status"] == "pending"
    assert result["agent_id"] == "research"
    assert result["risk_level"] in ("low", "medium", "high")
    sql = cur.execute.call_args[0][0]
    assert "INSERT INTO agent_submissions" in sql
    conn.commit.assert_called_once()


@pytest.mark.parametrize("payload", [
    {"agent_id": "", "agent_yaml": {}},
    {"agent_id": "ok", "agent_yaml": "not-a-dict"},
    {"agent_id": "ok", "agent_yaml": {}},
])
def test_create_submission_rejects_invalid(payload):
    with _patch_pool() as (cur, _):
        with pytest.raises(ValueError):
            store.create_submission(**payload, author_id="user-1")
    cur.execute.assert_not_called()  # validation fails before touching the DB


def test_create_submission_duplicates_pending_raises_valueerror():
    with _patch_pool(
        execute_side_effect=UniqueViolation("duplicate key")
    ) as (cur, _):
        with pytest.raises(ValueError, match="pending submission already exists"):
            store.create_submission(
                agent_id="research",
                agent_yaml={"id": "research", "name": "R"},
                author_id="user-1",
            )


# --------------------------------------------------------------------------- #
# Store: list / get / review
# --------------------------------------------------------------------------- #

def test_list_submissions_emits_status_filter():
    with _patch_pool(fetchall_rows=[_row(agent_id="a", status="pending"), _row(agent_id="b", status="rejected")]) as (cur, _):
        rows = store.list_submissions(status="pending")
    # Filtering is SQL-side, so the mock returns all rows; assert the filter is emitted.
    assert len(rows) == 2
    sql, params = cur.execute.call_args[0]
    assert "status = %s" in sql
    assert "pending" in params


def test_get_submission_returns_row_or_none():
    with _patch_pool(fetchone_row=_row(agent_id="research")):
        found = store.get_submission(_UUID)
    assert found["agent_id"] == "research"
    with _patch_pool(fetchone_row=None):
        assert store.get_submission("00000000-0000-0000-0000-000000000000") is None


def test_review_submission_approve_updates_row():
    with _patch_pool(fetchone_row=_row(agent_id="research", status="approved", reviewed_by="admin-1")) as (cur, conn):
        result = store.review_submission(
            submission_id=_UUID, decision="approve", reviewed_by="admin-1", review_notes="looks good"
        )
    assert result["status"] == "approved"
    sql = cur.execute.call_args[0][0]
    assert "UPDATE agent_submissions" in sql and "approved" in sql
    conn.commit.assert_called_once()


def test_review_submission_reject_updates_row():
    with _patch_pool(fetchone_row=_row(agent_id="research", status="rejected")):
        result = store.review_submission(submission_id=_UUID, decision="reject", reviewed_by="admin-1")
    assert result["status"] == "rejected"


def test_review_submission_unknown_decision_rejected():
    with _patch_pool() as (cur, _):
        with pytest.raises(ValueError):
            store.review_submission(submission_id=_UUID, decision="maybe", reviewed_by="admin-1")
    cur.execute.assert_not_called()


def test_set_materialize_error_marks_row():
    with _patch_pool(rowcount=1) as (cur, conn):
        store.set_materialize_error(_UUID, "fs write failed")
    sql = cur.execute.call_args[0][0]
    assert "materialize_error" in sql
    conn.commit.assert_called_once()


# --------------------------------------------------------------------------- #
# Materialize
# --------------------------------------------------------------------------- #

def test_materialize_writes_files_and_reloads(tmp_path):
    reload_calls = []

    def _reload() -> None:
        reload_calls.append(True)

    submission = {
        "agent_id": "research",
        "agent_yaml": {"id": "research", "name": "Research", "description": "r"},
        "system_prompt": "You are a research assistant.",
    }
    result = materialize.materialize_submission(
        submission=submission,
        plugins_dir=tmp_path,
        reload_agent_registry=_reload,
    )
    assert result["ok"]
    yaml_path = tmp_path / "research" / "agent.yaml"
    prompt_path = tmp_path / "research" / "system_prompt.md"
    assert yaml_path.exists()
    assert prompt_path.exists()
    assert yaml_path.read_text().startswith("id: research")
    assert reload_calls == [True]


def test_materialize_without_prompt_skips_md(tmp_path):
    submission = {"agent_id": "research", "agent_yaml": {"id": "research", "name": "R"}}
    result = materialize.materialize_submission(submission=submission, plugins_dir=tmp_path)
    assert result["ok"]
    assert not (tmp_path / "research" / "system_prompt.md").exists()


def test_materialize_captures_oserror(tmp_path, monkeypatch):
    from pathlib import Path as _Path

    real_write = _Path.write_text

    def _boom(self, *args, **kwargs):
        raise OSError("read-only filesystem")

    monkeypatch.setattr(_Path, "write_text", _boom)
    submission = {"agent_id": "research", "agent_yaml": {"id": "research", "name": "R"}}
    result = materialize.materialize_submission(submission=submission, plugins_dir=tmp_path)
    assert not result["ok"]
    assert "filesystem write failed" in result["error"]


# --------------------------------------------------------------------------- #
# Use cases: orchestration + review triggers materialize
# --------------------------------------------------------------------------- #

def test_review_approve_triggers_materialize_and_records_ok():
    updated = _row(agent_id="research", status="approved")
    with patch.object(services.store, "review_submission", return_value=updated), \
         patch.object(services.store, "get_submission", return_value=updated), \
         patch.object(services.materialize, "materialize_submission", return_value={"ok": True, "written": []}) as mat:
        result = services.review_submission(
            submission_id=_UUID, decision="approve", reviewed_by="admin-1"
        )
    mat.assert_called_once()
    assert result["materialize"]["ok"]
    assert result["submission"]["status"] == "approved"


def test_review_reject_does_not_materialize():
    updated = _row(agent_id="research", status="rejected")
    with patch.object(services.store, "review_submission", return_value=updated), \
         patch.object(services.materialize, "materialize_submission") as mat:
        result = services.review_submission(
            submission_id=_UUID, decision="reject", reviewed_by="admin-1"
        )
    mat.assert_not_called()
    assert result["materialize"] is None


def test_review_approve_records_materialize_error_on_failure():
    updated = _row(agent_id="research", status="approved")
    with patch.object(services.store, "review_submission", return_value=updated), \
         patch.object(services.store, "get_submission", return_value=_row(
             agent_id="research", status="approved", materialize_error="fs failed")), \
         patch.object(services.materialize, "materialize_submission",
                      return_value={"ok": False, "error": "fs failed"}) as mat, \
         patch.object(services.store, "set_materialize_error") as mark:
        result = services.review_submission(
            submission_id=_UUID, decision="approve", reviewed_by="admin-1"
        )
    mat.assert_called_once()
    mark.assert_called_once_with(_UUID, "fs failed")
    assert result["submission"]["materialize_error"] == "fs failed"


def test_preview_submission_enriches_with_yaml_and_warnings():
    row = _row(agent_id="research", agent_yaml={"id": "research", "name": "R", "tool_allowlist": ["ghost_tool"]})
    with patch.object(services.store, "get_submission", return_value=row):
        data = services.preview_submission(_UUID)
    assert data["yaml_text"].startswith("id: research")
    assert "ghost_tool" in data["tool_warnings"]


def test_preview_submission_missing_returns_none():
    with patch.object(services.store, "get_submission", return_value=None):
        assert services.preview_submission(_UUID) is None
