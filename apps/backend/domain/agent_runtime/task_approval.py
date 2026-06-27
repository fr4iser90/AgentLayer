"""Task status gates: non-admin users need approval before ``queued`` execution."""

from __future__ import annotations

from typing import Literal

TaskStatus = Literal["draft", "planning", "queued", "in_progress", "blocked", "done", "cancelled"]


def normalize_new_task_status(
    *,
    requested: str | None,
    user_role: str | None,
) -> tuple[TaskStatus, str | None]:
    """
    Return (effective_status, hint).

    Admins may create ``queued`` tasks directly. Other roles are downgraded to
    ``draft`` until they explicitly approve (``task_update`` → ``queued``).
    """
    role = (user_role or "user").strip().lower()
    raw = (requested or "draft").strip().lower()
    if raw not in ("draft", "planning", "queued", "in_progress", "blocked", "done", "cancelled"):
        raw = "draft"
    if raw == "queued" and role != "admin":
        return "draft", (
            "Task saved as draft — approval required before execution. "
            "Call task_update with status=queued when ready (admin users may queue directly)."
        )
    return raw, None  # type: ignore[return-value]


def may_transition_to_queued(*, user_role: str | None) -> tuple[bool, str | None]:
    role = (user_role or "user").strip().lower()
    if role == "admin":
        return True, None
    return True, (
        "Non-admin queued task — will run when the task runner picks it up "
        "(ensure you intend to execute this work)."
    )
