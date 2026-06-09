# Test layout

```
tests/
├── unit/                    # Fast pytest — backend logic, mocks, no server
│   └── test_<module>.py
├── e2e/
│   ├── support/             # Shared E2E library (NOT pytest entry points)
│   │   ├── helpers.py       # E2EClient, auth, env
│   │   ├── chat_ws.py
│   │   ├── idor.py
│   │   ├── cleanup.py
│   │   └── auth_refresh_scaling.py
│   └── test_<scenario>.py   # Live HTTP/WS (@pytest.mark.e2e)
└── benchmarks/
    ├── agent/
    │   ├── *.py             # Harness, cases, rubrics (library)
    │   └── test_*.py        # Pytest (live runs: @pytest.mark.benchmark)
    └── retrieval/
        ├── *.py
        └── test_*.py
```

## Naming rules

| Location | Pattern | Example |
|----------|---------|---------|
| `tests/unit/` | `test_<domain>_<feature>.py` | `test_agent_access.py` |
| `tests/unit/` (E2E lib tests) | `test_support_<lib>.py` | `test_support_cleanup.py` |
| `tests/e2e/` | `test_<scenario>.py` only | `test_auth_idor_matrix.py` |
| `tests/e2e/support/` | no `test_` prefix | `helpers.py`, `cleanup.py` |
| `tests/benchmarks/**/` | lib without prefix; pytest with `test_` | `harness.py`, `test_catalog.py` |

All pytest entry points use the `test_` prefix. Library/support code never does.

## Commands

| Suite | Command |
|-------|---------|
| **Unit + bench helpers** (pre-commit) | `PYTHONPATH=. pytest tests/unit tests/benchmarks -m "not e2e and not benchmark" -q` |
| **Unit only** | `./scripts/run-unit-tests.sh` |
| **E2E** | `./scripts/run-e2e-journeys.sh` |
| **Agent benchmark (live LLM)** | `AGENT_BENCH_LIVE=1 ./scripts/run-agent-benchmark-pytest.sh` |

## Markers

- `e2e` — running server on :8088 + LLM catalog
- `benchmark` — live model runs; skipped unless `AGENT_BENCH_LIVE=1`
