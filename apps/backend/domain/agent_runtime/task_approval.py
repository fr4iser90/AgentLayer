"""Task status gates: only site admins may create a task that is already ``queued``."""

from __future__ import annotations

from typing import Literal

TaskStatus = Literal["draft", "planning", "queued", "in_progress", "blocked", "done", "cancelled"]


def normalize_new_task_status(
    *,
    requested: str | None,
    site_role: str | None,
) -> tuple[TaskStatus, str | None]:
    """
    Return (effective_status, hint).

    Site admins may create ``queued`` tasks directly. Other accounts are
    downgraded to ``draft`` until they queue it themselves (``task_update`` →
    ``queued``).

    ``site_role`` is the only elevation source here (ADR 0011 §1). This took
    ``user_role`` — the legacy ``users.role``, which a demotion does not rewrite —
    so an account with ``site_role='site_user'`` still carrying ``role='admin'``
    kept straight-through queueing while an admin from before the column lost it.
    There is deliberately no parameter for that value: callers resolve it through
    ``db.user_site_role``, which honours the legacy column only where
    ``site_role`` is unknown.
    """
    raw = (requested or "draft").strip().lower()
    if raw not in ("draft", "planning", "queued", "in_progress", "blocked", "done", "cancelled"):
        raw = "draft"
    if raw == "queued" and str(site_role or "").strip().lower() != "site_admin":
        return "draft", (
            "Task saved as draft — approval required before execution. "
            "Call task_update with status=queued when ready (site admins may queue directly)."
        )
    return raw, None  # type: ignore[return-value]
