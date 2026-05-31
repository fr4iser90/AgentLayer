#!/usr/bin/env python3
"""Print tool domains and handler names from the live registry.

Usage:
  python scripts/list_tool_domains.py
  python scripts/list_tool_domains.py --agents
  python scripts/list_tool_domains.py --markdown
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _domain_tools() -> dict[str, list[str]]:
    from apps.backend.domain.plugin_system.registry import get_registry

    reg = get_registry()
    by_domain: dict[str, set[str]] = defaultdict(set)
    for entry in reg._tools_meta:
        domain = str(entry.get("domain") or "?").lower()
        for name in entry.get("tools") or []:
            if name:
                by_domain[domain].add(str(name))
    return {d: sorted(names) for d, names in sorted(by_domain.items())}


def _agent_summary() -> list[tuple[str, list[str], int]]:
    from apps.backend.domain.agent_registry import get_agent_registry

    reg = get_agent_registry()
    rows: list[tuple[str, list[str], int]] = []
    for agent in reg.list_agents():
        aid = str(agent.get("id") or "")
        if not aid:
            continue
        full = reg.get_agent(aid)
        if not full:
            continue
        domains = list(full.get("tool_domains") or [])
        rows.append((aid, domains, len(full.get("tool_names") or [])))
    return sorted(rows, key=lambda r: r[0])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--agents", action="store_true", help="Include agent → domain mapping")
    parser.add_argument("--markdown", action="store_true", help="Markdown table output")
    args = parser.parse_args()

    domains = _domain_tools()
    total_tools = sum(len(v) for v in domains.values())

    if args.markdown:
        print("| Domain | Tools | Handler names |")
        print("|--------|------:|---------------|")
        for domain, names in domains.items():
            preview = ", ".join(names[:8])
            if len(names) > 8:
                preview += ", …"
            print(f"| `{domain}` | {len(names)} | {preview} |")
        print()
        print(f"**Total:** {len(domains)} domains, {total_tools} handler names")
        if args.agents:
            print()
            print("| Agent | Domains | Resolved tools |")
            print("|-------|---------|---------------:|")
            for aid, doms, count in _agent_summary():
                print(f"| `{aid}` | {', '.join(f'`{d}`' for d in doms) or '—'} | {count} |")
        return 0

    print(f"Tool domains ({len(domains)} domains, {total_tools} handler names)\n")
    for domain, names in domains.items():
        print(f"{domain}\t{len(names)}\t{', '.join(names)}")

    if args.agents:
        print("\nAgents\n")
        for aid, doms, count in _agent_summary():
            dom_str = ", ".join(doms) if doms else "—"
            print(f"{aid}\t{count} tools\tdomains: {dom_str}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
