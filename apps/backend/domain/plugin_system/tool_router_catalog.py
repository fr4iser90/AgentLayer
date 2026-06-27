from __future__ import annotations

from typing import Any


class _RouterAccum:
    """Mutable state while scanning modules for router metadata."""

    __slots__ = ("cat_TOOL_DESCRIPTION", "cat_TOOL_LABEL", "order", "tools", "TOOL_TRIGGERS")

    def __init__(self) -> None:
        self.tools: dict[str, set[str]] = {}
        self.TOOL_TRIGGERS: dict[str, set[str]] = {}
        self.order: list[str] = []
        self.cat_TOOL_LABEL: dict[str, str] = {}
        self.cat_TOOL_DESCRIPTION: dict[str, str] = {}


def router_category_order(registry: Any, deps: Any) -> list[str]:
    """Call with registry lock held."""
    known = frozenset(registry._router_cat_tools.keys())
    order: list[str] = []
    seen: set[str] = set()
    for c in deps.effective_domain_order():
        if c in known and c not in seen:
            order.append(c)
            seen.add(c)
    for c in registry._router_cat_order:
        if c in known and c not in seen:
            order.append(c)
            seen.add(c)
    return order


def domain_trigger_substrings(registry: Any, deps: Any, domain: str) -> tuple[str, ...]:
    key = (domain or "").strip().lower()
    if not key:
        return ()
    with registry._lock:
        raw = registry._router_cat_TOOL_TRIGGERS.get(key, frozenset())
    base = {str(x).strip().lower() for x in raw if str(x).strip()}
    try:
        base.update(deps.overlay_phrases_for_domain(key))
    except Exception:
        pass
    return tuple(sorted(base))


def list_router_categories_catalog(registry: Any, order: list[str]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for cid in order:
        tools = registry._router_cat_tools.get(cid)
        if not tools:
            continue
        label = registry._router_cat_TOOL_LABEL.get(cid) or cid
        desc = registry._router_cat_TOOL_DESCRIPTION.get(cid) or ""
        out.append(
            {
                "id": cid,
                "TOOL_LABEL": label,
                "TOOL_DESCRIPTION": desc,
                "tool_count": len(tools),
            }
        )
    return out


def list_router_category_tools_lite(registry: Any, category: str) -> list[dict[str, str]]:
    c = category.strip().lower()
    with registry._lock:
        names = registry._router_cat_tools.get(c)
        if not names:
            return []
        name_set = set(names)
        rows: list[dict[str, str]] = []
        for spec in registry._chat_tool_specs:
            fn = spec.get("function") if isinstance(spec, dict) else None
            if not isinstance(fn, dict):
                continue
            n = fn.get("name")
            if not n or n not in name_set:
                continue
            rows.append(
                {
                    "name": str(n),
                    "TOOL_DESCRIPTION": (fn.get("TOOL_DESCRIPTION") or "").strip(),
                }
            )
    rows.sort(key=lambda r: r["name"])
    return rows


def classify_tool_router_categories(registry: Any, order: list[str], user_text: str) -> frozenset[str]:
    if not (user_text or "").strip():
        return frozenset()
    tl = user_text.lower()
    with registry._lock:
        triggers_map = registry._router_cat_TOOL_TRIGGERS
    matched: set[str] = set()
    for cat in order:
        for sub in triggers_map.get(cat, frozenset()):
            if sub and sub in tl:
                matched.add(cat)
                break
    return frozenset(matched)


def classify_tool_router_category(order: list[str], cats: frozenset[str]) -> str | None:
    if not cats:
        return None
    for c in order:
        if c in cats:
            return c
    return next(iter(cats))


__all__ = [
    "_RouterAccum",
    "classify_tool_router_categories",
    "classify_tool_router_category",
    "domain_trigger_substrings",
    "list_router_categories_catalog",
    "list_router_category_tools_lite",
    "router_category_order",
]
