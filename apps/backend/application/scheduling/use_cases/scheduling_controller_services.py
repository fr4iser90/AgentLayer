from __future__ import annotations
from typing import Any

from apps.backend.infrastructure.dashboards.dashboard_persistence import dashboard_access_ex
from apps.backend.infrastructure.db import db
from apps.backend.infrastructure.platform.config import PLUGINS_DIR
from apps.backend.infrastructure.projects import project_runs_store
from apps.backend.infrastructure.scheduling import scheduler_job_runs_store, scheduler_jobs_store


def normalize_coding_workflow(wf: dict[str, Any], *, require_workspace: bool = False) -> dict[str, Any]:
    """Stub: coding workflows removed. Returns dict as-is."""
    return dict(wf) if wf else {}
