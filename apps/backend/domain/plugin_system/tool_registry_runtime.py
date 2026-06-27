from __future__ import annotations

import inspect
import json
from typing import Any


def tool_names_for_capabilities(registry: Any, *capabilities: str) -> list[str]:
    """Registered tool function names declaring any of ``capabilities``."""
    want = {str(c).strip() for c in capabilities if str(c).strip()}
    if not want:
        return []
    out: list[str] = []
    with registry._lock:
        for entry in registry._tools_meta:
            tlist = entry.get("tools")
            if not isinstance(tlist, list):
                continue
            per = entry.get("per_tool") if isinstance(entry.get("per_tool"), dict) else {}
            mod_caps = entry.get("capabilities")
            mod_cap_set = (
                {str(x).strip() for x in mod_caps if str(x).strip()}
                if isinstance(mod_caps, list)
                else set()
            )
            for tn in tlist:
                n = str(tn).strip()
                if not n:
                    continue
                caps: set[str] = set(mod_cap_set)
                row = per.get(n) if isinstance(per, dict) else None
                if isinstance(row, dict):
                    rc = row.get("capabilities")
                    if isinstance(rc, list):
                        caps.update(str(x).strip() for x in rc if str(x).strip())
                if caps & want and n not in out:
                    out.append(n)
    return out


def run_tool(registry: Any, deps: Any, name: str, arguments: dict[str, Any], context: dict | None = None) -> str:
    with registry._lock:
        handler = registry._handlers.get(name)
    if not handler:
        return json.dumps({"ok": False, "error": f"unknown tool: {name}"})
    ok = True
    try:
        sig = inspect.signature(handler) if hasattr(handler, "__call__") else None
        if sig and "context" in sig.parameters:
            out = handler(dict(arguments or {}), context=context)
        else:
            out = handler(dict(arguments or {}))
        payload = json.loads(out) if out else {}
        if isinstance(payload, dict) and payload.get("ok") is False:
            ok = False
    except Exception as e:
        ok = False
        out = json.dumps({"ok": False, "error": str(e)})
    from apps.backend.domain.tools.invocation_context import get_agent_run_id

    rid = get_agent_run_id()
    deps.log_tool_invocation(
        name, dict(arguments or {}), out, ok, agent_run_id=rid
    )
    return out


__all__ = ["run_tool", "tool_names_for_capabilities"]
