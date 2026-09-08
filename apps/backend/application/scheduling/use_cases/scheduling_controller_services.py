from __future__ import annotations

from typing import Any
import uuid

from apps.backend.infrastructure.codebase.coding_workflow import normalize_coding_workflow
from apps.backend.infrastructure.dashboards.dashboard_persistence import dashboard_access_ex
from apps.backend.infrastructure.db import db
from apps.backend.infrastructure.platform.config import PLUGINS_DIR
from apps.backend.infrastructure.projects import project_runs_store
from apps.backend.infrastructure.scheduling import scheduler_job_runs_store, scheduler_jobs_store
from apps.backend.infrastructure.scheduling.schedules_access import (
    schedule_feature_permission_error as _schedule_feature_permission_error,
    user_may_use_schedules as _user_may_use_schedules,
)


def user_may_use_schedules(
    *,
    user_id: uuid.UUID | None = None,
    user_role: str | None = None,
    user: Any | None = None,
) -> bool:
    return _user_may_use_schedules(user_id=user_id, user_role=user_role, user=user)


def schedule_feature_permission_error(
    *,
    user_id: uuid.UUID | None = None,
    user_role: str | None = None,
    user: Any | None = None,
) -> str | None:
    return _schedule_feature_permission_error(user_id=user_id, user_role=user_role, user=user)
