#!/usr/bin/env python3
"""Measure what an agent's tools[] payload costs in catalog vs full-schema mode.

Answers the practical question before tuning ratios: can we afford to send real
JSON Schemas for every tool an agent declares, on a given context window?
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

# Composition root: binds the domain registries to real plugin scanning (see tests/unit/conftest.py).
from apps.backend.infrastructure.agent_runtime import agent_registry_service  # noqa: E402,F401
from apps.backend.infrastructure.plugins import plugin_registry_service  # noqa: E402,F401
from apps.backend.domain.agent_runtime.registry import get_agent_registry  # noqa: E402
from apps.backend.domain.agent_runtime.tool_catalog import (  # noqa: E402
    _catalog_tool_function,
    _full_schema_tool_function,
    _tool_spec_name,
)
from apps.backend.domain.plugin_system.registry import get_registry  # noqa: E402

CHARS_PER_TOKEN = 4
WINDOWS = (8192, 16384, 32768, 65536, 131072)
AGENTS = ("coding", "coding_plan", "security_auditor", "general", "knowledge_companion")


def _tokens(specs: list[dict]) -> int:
    payload = json.dumps(specs, ensure_ascii=False, separators=(",", ":"))
    return len(payload) // CHARS_PER_TOKEN


def main() -> int:
    reg = get_registry()
    reg.load_all()
    by_name = {n: s for s in reg.chat_tool_specs if (n := _tool_spec_name(s))}

    print(f"{'agent':<20} {'tools':>6} {'catalog':>9} {'full':>9} {'factor':>7}")
    print("-" * 56)
    rows: list[tuple[str, int, int, int]] = []
    for agent_id in AGENTS:
        agent = get_agent_registry().get_agent(agent_id)
        if not agent:
            print(f"{agent_id:<20} (not in registry)")
            continue
        names = [n for n in (agent.get("tool_names") or []) if n in by_name]
        catalog = [_catalog_tool_function(n, by_name[n]["function"]) for n in names]
        full = [_full_schema_tool_function(n, by_name[n]["function"]) for n in names]
        c_tok, f_tok = _tokens(catalog), _tokens(full)
        factor = (f_tok / c_tok) if c_tok else 0.0
        rows.append((agent_id, len(names), c_tok, f_tok))
        print(f"{agent_id:<20} {len(names):>6} {c_tok:>9} {f_tok:>9} {factor:>6.1f}x")

    print()
    print("Share of context window consumed by full schemas:")
    header = f"{'agent':<20}" + "".join(f"{w // 1024:>7}k" for w in WINDOWS)
    print(header)
    print("-" * len(header))
    for agent_id, _count, _c_tok, f_tok in rows:
        cells = "".join(f"{(f_tok / w) * 100:>7.0f}%" for w in WINDOWS)
        print(f"{agent_id:<20}{cells}")

    print()
    print("Required AGENT_TOOLS_BUDGET_RATIO to fit full schemas:")
    for agent_id, _count, _c_tok, f_tok in rows:
        needed = max((f_tok / w) for w in WINDOWS if w >= 16384)
        print(f"  {agent_id:<20} >= {needed:.3f} (at 16k) ")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
