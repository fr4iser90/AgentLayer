#!/usr/bin/env bash
# Fast backend tests: unit + benchmark helpers (no server, no live LLM).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
exec python3 -m pytest tests/unit tests/benchmarks -m "not e2e and not benchmark" -v --tb=short "$@"
