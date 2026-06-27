# Scripts

This directory contains developer and operator entry points. Keep root-level
scripts for stable commands referenced by docs, tests, Docker, or common local
workflows. Put scoped helpers in subdirectories.

## Stable Entry Points

- `checks/run.py` - modular repository checks configured by `checks/config.json`.
- `pre-commit-check.sh` - git pre-commit entry point for modular checks.
- `install-git-pre-commit-hook.sh` - installs `.git/hooks/pre-commit`.
- `alembic_entrypoint.sh` - Docker migration entry point.
- `run-unit-tests.sh` - unit test runner.
- `run-e2e-journeys.sh` - live E2E journey runner.
- `run-e2e-playwright-i18n.sh` - Playwright i18n runner.
- `run-agent-benchmark-pytest.sh` - pytest wrapper for live agent benchmarks.
- `run_agent_benchmark.py` - CLI runner for agent benchmark manifests.
- `run_retrieval_benchmark.py` - CLI runner for retrieval benchmarks.
- `bench_cleanup.py` - cleanup benchmark sandbox resources.
- `e2e_cleanup.py` - cleanup E2E/IDOR sandbox resources.
- `reindex_agentlayer_docs.py` - operator helper for docs RAG ingestion.
- `memory_graph_stats.py` - operator diagnostic for memory graph stats.
- `list_tool_domains.py` - registry inventory helper; used to regenerate docs.

## Subdirectories

- `checks/` - modular precommit/CI check framework.
- `diag/` - local performance diagnostics for auth/runtime/bootstrap paths.
- `e2e/` - support scripts used by E2E runners.

## Cleanup Candidates

These look like migration or one-shot maintenance scripts. Keep them only if the
workflow is still expected to be rerun; otherwise move the knowledge into docs
and remove the script in a dedicated cleanup change.

- `migrate_tool_triggers_to_router_yaml.py` - one-shot migration from Python
  `TOOL_TRIGGERS` constants to co-located router YAML.
- `add_de_router_phrases.py` - bulk helper for adding German router phrases.
- `e2e_auth_smoke.py` - authenticated smoke probe for SPA/API routes. Either
  document it as a supported E2E diagnostic or remove it if the E2E journeys
  supersede it.

## Maintenance Rules

- New reusable commands should have a short module docstring with usage.
- New one-shot migrations should include `One-shot:` in the docstring and an
  expected removal condition.
- Prefer adding a check under `checks/checks/` over ad hoc validation scripts.
- If a root script is not referenced by docs, tests, Docker, or regular operator
  workflows, move it under an appropriate subdirectory or remove it.
