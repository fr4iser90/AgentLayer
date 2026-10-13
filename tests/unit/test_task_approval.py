"""Task approval policy for queued agent tasks.

The elevation source behind these calls is pinned per actor, including a demoted
account whose legacy ``users.role`` still says ``admin``, in
``test_task_approval_uses_site_role.py``.
"""

from apps.backend.domain.agent_runtime.task_approval import normalize_new_task_status


def test_non_admin_queued_becomes_draft():
    status, hint = normalize_new_task_status(requested="queued", site_role="site_user")
    assert status == "draft"
    assert hint


def test_admin_may_queue():
    status, hint = normalize_new_task_status(requested="queued", site_role="site_admin")
    assert status == "queued"
    assert hint is None


def test_default_draft():
    status, hint = normalize_new_task_status(requested=None, site_role="site_user")
    assert status == "draft"
    assert hint is None
