# LLM benchmark — implementation checklist

Full plan: [docs/benchmarks/agent-llm-benchmark.md](docs/benchmarks/agent-llm-benchmark.md)

## Phase 0 — smoke ✅

## Phase 1 — modular harness ✅

- [x] Fixture layer (`tests/benchmarks/agent/fixtures.py`)
- [x] Manifest suites under `benchmarks/manifests/`
- [x] Workspace variants (W1, W2 indexed / no index)
- [x] Social fixture (friend + block share) + SOC1
- [x] Gmail integration fixture (skip without secret)
- [x] Cleanup hint with run-specific prefix

**Suites** (all via **Admin → Observability → Model benchmarks** `/admin/benchmarks`):

| Manifest | Fixtures | Scenarios |
|----------|----------|-----------|
| `manifests/smoke.yaml` | agentlayer_self (S3) | S1–S3 |
| `manifests/workspace.yaml` | workspace_git, workspace_indexed | W1, W2×2 |
| `manifests/social.yaml` | friend_pair, dashboard_block_share | SOC1 (block share / read shared data) |
| `manifests/dashboards.yaml` | dashboard_empty (D2) | D1 create, D2 layout patch |
| `manifests/integrations.yaml` | gmail_secret | INT1 |
| `manifests/coding.yaml` | workspace_git | C1, C2 |
| `manifests/security.yaml` | workspace_agentlayer_git, ssc_secret | SEC1, SEC2 |

**Run:** Admin UI (`/admin/benchmarks`) — LLM endpoints from **Admin → Interfaces** (DB). Optional secrets in `.env`.

## Phase 2 — Admin UI ✅ (basic)

- [x] `GET/POST /v1/admin/benchmarks/*`
- [x] DB `benchmark_runs` (schema_090)
- [x] Admin → Observability → Model benchmarks (`/admin/benchmarks`)
- [x] Suite catalog: scenarios, fixtures, prompts, expected tools (modular pick)
- [ ] Capability matrix / routing tags (later)

## Phase 3 — tier 2–3 product scenarios

- [x] C1 coding via `project_run` (poll, result_json, git metrics)
- [x] Suite `benchmarks/manifests/coding.yaml` (hours timeout)
- [x] D1 dashboard create via agent
- [x] D2 layout patch (markdown + notes dataPath)
- [x] SOC1 block share (separate social suite — agent reads shared data, not create/layout)
- [x] C2 coding edits (README line + git diff via API)
- [x] pytest `-m benchmark` live gate (`test_live_benchmark.py`, `scripts/run-agent-benchmark-pytest.sh`) — manual only

## Phase 3 — security + ops (optional)

- [x] AgentLayer git fixture (`workspace_agentlayer_git`)
- [x] SSC secret fixture (`ssc_secret`, skips without `AGENT_BENCH_SSC_SECRET`)
- [x] SEC1 chat scan + SEC2 project_run remediation
- [x] Suite `benchmarks/manifests/security.yaml`
