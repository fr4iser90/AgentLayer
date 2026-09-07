from __future__ import annotations

from apps.backend.infrastructure.codebase.coding_workflow import normalize_coding_workflow
from apps.backend.infrastructure.dashboards.dashboard_persistence import dashboard_access_ex
from apps.backend.infrastructure.db import db
from apps.backend.infrastructure.platform.config import PLUGINS_DIR
from apps.backend.infrastructure.projects import project_runs_store
from apps.backend.infrastructure.scheduling import scheduler_job_runs_store, scheduler_jobs_store
