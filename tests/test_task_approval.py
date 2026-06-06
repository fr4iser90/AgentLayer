"""Task approval policy for queued agent tasks."""

from apps.backend.domain.task_approval import normalize_new_task_status


def test_non_admin_queued_becomes_draft():
    status, hint = normalize_new_task_status(requested="queued", user_role="user")
    assert status == "draft"
    assert hint


def test_admin_may_queue():
    status, hint = normalize_new_task_status(requested="queued", user_role="admin")
    assert status == "queued"
    assert hint is None


def test_default_draft():
    status, hint = normalize_new_task_status(requested=None, user_role="user")
    assert status == "draft"
    assert hint is None
