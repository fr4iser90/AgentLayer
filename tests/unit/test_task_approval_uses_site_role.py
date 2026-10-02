"""Creating a task straight in ``queued`` asks ``users.site_role`` — never ``users.role``.

``task_create`` used to read the legacy column and hand it to
``domain/agent_runtime/task_approval.normalize_new_task_status``, which is the rule that
decides whether a requested ``queued`` survives or lands as ``draft``. ADR 0011 §1 left
``users.role`` as a compatibility column and demotion does not rewrite it, so an account
with ``site_role='site_user'`` that still carried ``role='admin'`` kept creating tasks
that the runner picks up immediately, and there was nothing an admin could flip to take
that back. The other direction was broken too: a site admin from before the column, with
only ``role='user'``, was downgraded on every create.

What the rule opens is narrower than the other doors in this migration and the test says
so: it decides whether the first row is ``draft`` or ``queued``, not who approves a run —
``task_update`` moves any task the caller may see to ``queued`` for every account.

Pinned per actor and by source scan, because the read and the rule sit in two different
layers: ``plugins/tools/platform/tasks/agent_tasks.py`` feeds
``apps/backend/domain/agent_runtime/task_approval.py``.
"""

from __future__ import annotations

import ast
import inspect
import json
import uuid
from pathlib import Path
from typing import Any
from unittest.mock import patch

import plugins.tools.platform.tasks.agent_tasks as task_tool
from apps.backend.domain.agent_runtime import task_approval

REPO_ROOT = Path(__file__).resolve().parents[2]

DEMETED = uuid.uuid4()  # role='admin', site_role='site_user'
SITE_ADMIN = uuid.uuid4()  # site_role='site_admin'
PLAIN = uuid.uuid4()  # site_role='site_user'
TENANT = 7

# (label, user id, may create a queued task)
ACTORS: list[tuple[str, uuid.UUID, bool]] = [
    ("demoted legacy admin", DEMETED, False),
    ("site admin", SITE_ADMIN, True),
    ("plain member", PLAIN, False),
]

_SCANNED = (
    "plugins/tools/platform/tasks/agent_tasks.py",
    "apps/backend/domain/agent_runtime/task_approval.py",
)


def _site_roles() -> dict[str, str]:
    return {str(DEMETED): "site_user", str(SITE_ADMIN): "site_admin", str(PLAIN): "site_user"}


def _create_task_status(user_id: uuid.UUID) -> tuple[str, str | None]:
    """Run the real ``task_create`` body and report what status reached the store.

    The legacy reader answers ``admin`` for every id: a create that still consults it
    queues for all three actors and this assertion cannot be satisfied.
    """
    captured: dict[str, Any] = {}

    def _create_task(**kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        return {"id": uuid.uuid4()}

    with (
        patch.object(task_tool, "get_identity", return_value=(TENANT, user_id)),
        patch(
            "apps.backend.infrastructure.db.db.user_site_role",
            side_effect=lambda uid, **_kw: _site_roles().get(str(uid), "site_user"),
        ),
        patch("apps.backend.infrastructure.db.db.user_role", return_value="admin"),
        patch.object(task_tool.agent_tasks_store, "create_task", side_effect=_create_task),
        patch.object(task_tool.agent_tasks_store, "row_to_public", return_value={}),
    ):
        payload = json.loads(task_tool.task_create({"goal": "ship it", "status": "queued"}, None))

    assert payload["ok"] is True, payload
    return str(captured["status"]), payload.get("approval_hint")


# ---------------------------------------------------------------------------
# The rule itself, one demoted account against a site admin.


def test_a_demoted_account_may_not_create_a_queued_task() -> None:
    status, hint = task_approval.normalize_new_task_status(requested="queued", site_role="site_user")
    assert status == "draft"
    assert hint


def test_a_site_admin_may_create_a_queued_task() -> None:
    status, hint = task_approval.normalize_new_task_status(requested="queued", site_role="site_admin")
    assert status == "queued"
    assert hint is None


def test_an_unknown_site_role_denies() -> None:
    """Nothing elevates on a missing value — the hint is the safe answer."""
    for raw in (None, "", "  ", "siteuser", "ADMIN"):
        status, hint = task_approval.normalize_new_task_status(requested="queued", site_role=raw)
        assert status == "draft", raw
        assert hint


def test_the_default_stays_draft_and_strangers_are_normalised() -> None:
    assert task_approval.normalize_new_task_status(requested=None, site_role="site_user") == ("draft", None)
    assert task_approval.normalize_new_task_status(requested="nonsense", site_role="site_admin") == ("draft", None)
    assert task_approval.normalize_new_task_status(requested="done", site_role="site_user") == ("done", None)


# ---------------------------------------------------------------------------
# The tool: the value handed to the rule must come from the canonical resolver.


def test_task_create_queues_only_for_the_site_admin() -> None:
    for label, user_id, may_queue in ACTORS:
        status, hint = _create_task_status(user_id)
        assert status == ("queued" if may_queue else "draft"), label
        assert bool(hint) is not may_queue, label


# ---------------------------------------------------------------------------
# Source scan: the read moved out of the domain rule into a caller, so a re-introduced
# legacy read would sit two layers away from the right it opens.


def test_neither_file_reads_the_legacy_role_column() -> None:
    for rel in _SCANNED:
        tree = ast.parse((REPO_ROOT / rel).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and ast.unparse(node.func) in {"db.user_role", "user_role"}:
                raise AssertionError(f"{rel}:{node.lineno} reads the legacy users.role")


def test_no_approval_rule_accepts_a_role_string() -> None:
    """A parameter that can hold ``users.role`` is the way this comes back."""
    for name, fn in vars(task_approval).items():
        if name.startswith("_") or not callable(fn) or getattr(fn, "__module__", None) != task_approval.__name__:
            continue
        for param in inspect.signature(fn).parameters:
            assert param not in {"user_role", "role"}, f"{name} takes {param!r} again"


def test_the_source_passes_the_canonical_read_to_the_rule() -> None:
    src = (REPO_ROOT / "plugins/tools/platform/tasks/agent_tasks.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and ast.unparse(node.func).endswith("normalize_new_task_status")
    ]
    assert calls, "task_create no longer asks the approval rule at all"
    for node in calls:
        args = {kw.arg: ast.unparse(kw.value) for kw in node.keywords}
        assert "site_role" in args, f"line {node.lineno} does not pass site_role"
        assert "user_site_role" in args["site_role"], f"line {node.lineno} feeds {args['site_role']!r}"
