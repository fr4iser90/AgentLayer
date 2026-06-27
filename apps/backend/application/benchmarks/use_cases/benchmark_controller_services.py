from __future__ import annotations

from apps.backend.infrastructure.agent_runtime import agent_config_service, agent_config_store
from apps.backend.infrastructure.agent_runtime.agent_config_fingerprint import compute_fingerprint
from apps.backend.infrastructure.benchmarks import benchmark_runs_store, benchmark_tuning_store
from apps.backend.infrastructure.benchmarks.benchmark_analysis import (
    _cohort_label_from_run,
    _fingerprint_from_run,
    analyze_runs,
    compare_cohorts,
    list_cohorts,
)
from apps.backend.infrastructure.benchmarks.benchmark_autotuner import (
    create_tuning_session,
    run_tuning_session,
    tuning_presets,
)
from apps.backend.infrastructure.benchmarks.benchmark_resource_service import (
    benchmark_sandbox_snapshot,
    prepare_benchmark_sandbox_cleanup,
)
from apps.backend.infrastructure.benchmarks.benchmark_review_service import run_review
from apps.backend.infrastructure.benchmarks.benchmark_runner import (
    benchmark_catalog,
    list_benchmark_llm_providers,
    list_suites,
    request_benchmark_cancel,
    start_benchmark_run,
)
from apps.backend.infrastructure.benchmarks.benchmark_stats import aggregate_benchmark_stats
from apps.backend.infrastructure.db import db
from apps.backend.infrastructure.platform.config import config
