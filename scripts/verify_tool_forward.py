#!/usr/bin/env python3
"""Verify what an agent's tools[] actually looks like after the forward plan.

Runs the real forward policy against the real plugin registry for a user message that
mentions no tool name, which is the case that used to shrink a declared allowlist down
to whatever happened to match a keyword.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

# Composition root: binds the domain registries to real plugin scanning.
from apps.backend.infrastructure.agent_runtime import agent_registry_service  # noqa: E402,F401
from apps.backend.infrastructure.plugins import plugin_registry_service  # noqa: E402,F401
from apps.backend.infrastructure.tools import tool_forward_policy_service  # noqa: E402,F401
from apps.backend.domain.agent_runtime.registry import get_agent_registry  # noqa: E402
from apps.backend.domain.agent_runtime.tool_catalog import _tool_spec_name  # noqa: E402
from apps.backend.domain.plugin_system.registry import get_registry  # noqa: E402
from apps.backend.domain.tools.forward_policy import (  # noqa: E402
    ToolForwardContext,
    build_tool_forward_plan,
)

# Deliberately names no tool and hits no router trigger.
USER_TEXT = "fix the login bug"
WINDOWS = (16384, 32768, 65536, 131072)
AGENTS = ("coding", "coding_plan", "security_auditor", "general")
# Tools a build agent is useless without; they never match a keyword in USER_TEXT.
MUST_HAVE = {
    "coding": ("bash", "edit", "apply_patch", "repository.read_file"),
    "coding_plan": ("repository.read_file", "repository.search"),
    "security_auditor": ("start", "findings"),
    "general": ("delegate",),
}


def main() -> int:
    reg = get_registry()
    reg.load_all()
    by_name = {n: s for s in reg.chat_tool_specs if (n := _tool_spec_name(s))}

    failures: list[str] = []
    print(f'user message: "{USER_TEXT}" (mentions no tool name)')
    print()
    header = f"{'agent':<18}{'declared':>9}" + "".join(f"{w // 1024:>9}k" for w in WINDOWS)
    print(header)
    print("-" * len(header))

    for agent_id in AGENTS:
        agent = get_agent_registry().get_agent(agent_id)
        if not agent:
            failures.append(f"{agent_id}: not in registry")
            continue
        specs = [by_name[n] for n in (agent.get("tool_names") or []) if n in by_name]
        cells = ""
        for window in WINDOWS:
            plan = build_tool_forward_plan(
                ToolForwardContext(
                    agent_id=agent_id,
                    model_id="verify",
                    context_window_tokens=window,
                    user_text=USER_TEXT,
                    tool_specs=specs,
                    ranking_enabled=True,
                    full_schema_preference=True,
                    has_explicit_allowlist=bool(agent.get("tool_allowlist")),
                )
            )
            cells += f"{len(plan.forward_names):>10}"
            modes = set(plan.schema_mode_per_tool.values())
            if modes and modes != {"full"}:
                failures.append(f"{agent_id} @{window}: schema modes {sorted(modes)} != full")
            if window >= 32768:
                if len(plan.forward_names) != len(specs):
                    failures.append(
                        f"{agent_id} @{window}: {len(plan.forward_names)}/{len(specs)} tools forwarded"
                    )
                missing = [t for t in MUST_HAVE.get(agent_id, ()) if t not in plan.forward_names]
                if missing:
                    failures.append(f"{agent_id} @{window}: missing {missing}")
        print(f"{agent_id:<18}{len(specs):>9}{cells}")

    print()
    if failures:
        print("FAILED:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("OK — declared allowlists survive an unrelated user message; schemas are full")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
